"""서비스 레이어: app/ 패키지(튜플/DataFrame 위주)를 API 응답에 맞는 JSON 친화적 구조(dict)로
변환하는 역할만 한다. HTTP 처리(views.py)와 실제 추론 로직(app/) 사이의 얇은 어댑터."""
import random
import time

from app.config import EMB_MODEL_NAME, EMB_MODEL_OPTIONS
from app.embedding import load_embedder, is_embedder_loaded
from app.models.classifier import (
    predict, load_model as _load_classifier_model, stage_to_subcategories as _stage_to_subcategories,
)
from app.nlp.keywords import extract_keyword_learned, load_keyword_model
from app.nlp.morphology import get_kiwi
from app.retrieval.gloss import (
    gloss_lookup_batch, load_gloss_dict, build_exact_gloss_index, build_gloss_synonym_embeddings,
    gloss_category_by_origin,
)
from app.retrieval.retriever import retrieve_answer, load_corpus, ground_truth_labels
from app.stats import compute_dataset_stats, compute_subcategory_stats

# cache_info().misses 증가 여부로 이번 요청에 콜드스타트(모델 로딩)가 포함됐는지 판단한다.
_LOADERS = [
    _load_classifier_model, _stage_to_subcategories, load_embedder,
    load_gloss_dict, build_exact_gloss_index, build_gloss_synonym_embeddings,
    get_kiwi, load_corpus, load_keyword_model, gloss_category_by_origin,
    compute_dataset_stats, compute_subcategory_stats,
]


def _total_cache_misses() -> int:
    return sum(loader.cache_info().misses for loader in _LOADERS)


def _resolve_model(emb_model):
    return emb_model or EMB_MODEL_NAME


def _model_label(model_id: str) -> str:
    return next((label for label, mid in EMB_MODEL_OPTIONS.items() if mid == model_id), model_id)


def classify(question: str, topk: int = 5) -> dict:
    stage_results, sub_results = predict(question, topk=topk)
    return {
        "stage_results": [{"label": label, "prob": prob} for label, prob in stage_results],
        "sub_results": [{"label": label, "prob": prob} for label, prob in sub_results],
    }


def retrieve(question: str, subcategories, top_k: int, max_examples: int, emb_model=None) -> dict:
    matches, used_filter = retrieve_answer(
        question, subcategories, top_k=top_k, max_examples=max_examples,
        model_name=_resolve_model(emb_model),
    )
    return {"matches": matches, "used_filter": used_filter}


def keywords(subcategory: str, answer: str) -> dict:
    """입력(세부분류, 환자 답변) -> 출력(대표 키워드 1개 + 신뢰도). SpanTagger(v2)가 세부분류
    맥락을 반영해 정보량 있는 표현 하나만 고른다(형태소분석으로 내용어 전체를 뽑는 방식은 미사용)."""
    keyword, confidence, _, _ = extract_keyword_learned(subcategory, answer)
    return {"keyword": keyword, "confidence": confidence}


def _gloss_result_to_dict(exact_hit, hits) -> dict:
    return {
        "exact": (
            {"name": exact_hit[0], "origin_number": exact_hit[1], "score": exact_hit[2]}
            if exact_hit else None
        ),
        "hits": [{"name": n, "origin_number": o, "score": s} for n, o, s in hits],
    }


def gloss(keywords, top_k: int, emb_model=None) -> dict:
    model_name = _resolve_model(emb_model)
    gloss_results = gloss_lookup_batch(keywords, top_k=top_k, model_name=model_name)
    return {
        "results": {
            kw: _gloss_result_to_dict(exact_hit, hits)
            for kw, (exact_hit, hits) in zip(keywords, gloss_results)
        }
    }


# "표현 가능한 글로스 없음" 판정(카드 단위)에만 쓰는 고정 임계값 - "근거로 인정"은 동적 값(아래) 사용.
RECOMMENDED_GLOSS_MIN_SCORE = 0.5

EVIDENCE_TOP_PERCENTILE = 0.15  # 상위 15%만 "근거 있음"으로 인정 (30%는 노이즈가 많아 되돌림)

EXCLUDED_SAMPLE_SIZE = 20  # 분석 패널에 보여줄 컷오프 제외 표제어 예시 개수

# 백분위 문턱은 사전 크기(655)에 비례해 항상 ~100개를 남기므로, 뒤쪽 대부분이 무관한 표제어로 채워진다.
# 절대 점수로 자르는 방식은 모델마다 유사도 스케일이 달라(측정: 같은 질문에서 0.65 이상이 10개 vs 461개)
# 못 쓰고, 세부분류에 따라 정답이 0.55~0.64에 몰리기도 해서 개수로 제한한다.
RECOMMENDED_GLOSS_MAX_COUNT = 30


# 세부분류별 실제 매칭 빈도가 높은 Gloss_Category 배치 집계 결과 중, 의미가 맞는 것만 수동 선별.
# 전체 세부분류에 기계적으로 적용하지 않는 이유: 흔한 시간부사 등이 무관한 세부분류에서도
# 임베딩 유사도상 우연히 1위로 잡히는 노이즈가 있어, 의미가 실제로 맞아떨어지는 것만 넣었다.
SUBCATEGORY_CATEGORY_PRIORITY: dict[str, set[str]] = {
    "location": {"일상생활 수어 > 인간 > 신체 부위 및 내부 구성", "일상생활 수어 > 개념 > 위치 및 방향"},
    "side": {"일상생활 수어 > 인간 > 신체 부위 및 내부 구성", "일상생활 수어 > 개념 > 위치 및 방향"},
    "chief_complaint": {"일상생활 수어 > 인간 > 신체 부위 및 내부 구성"},
    "surgery_site": {"일상생활 수어 > 인간 > 신체 부위 및 내부 구성"},
    "pain_score": {"일상생활 수어 > 개념 > 수"},
    "quality": {"일상생활 수어 > 개념 > 성질"},
    "prior_treatment": {"일상생활 수어 > 삶 > 치료"},
    "treatment_choice": {"일상생활 수어 > 삶 > 치료"},
}


# 카테고리보다 한 단계 더 좁힌 표제어 단위 가산점 - 배치 집계에서 의미가 확실히 맞는 것만 수동 선별
# (카테고리 필터만으로는 못 거르는 우연한 임베딩 매칭이 있어 개별 표제어 단위로 한 번 더 걸렀다).
SUBCATEGORY_GLOSS_PRIORITY: dict[str, set[int]] = {
    "location": {944, 4302, 537, 12028, 7364, 5468, 6864, 11004},  # 허리/팔꿈치/팔/엉덩이/다리/목/등/갈비뼈
    "side": {6036, 12035},  # 오른쪽/왼쪽
    "chief_complaint": {944, 4302, 12028, 6835, 6864, 7364, 537, 5468},  # 허리/팔꿈치/엉덩이/가슴/등/다리/팔/목
    "surgery_site": {944, 4302, 7364, 5468, 537, 12028, 6864, 6835, 11004},  # +갈비뼈
    "pain_score": {12707, 11419, 11055, 24029, 12397, 23841, 12528, 23851, 8944},  # 숫자(9/8/5/3/7/4/4/2) + 점수
    "quality": {10635, 8608, 10454, 11085, 7410, 5621, 6836, 11833},  # 부드럽다/강하다/묵직하다/무겁다/두껍다/아프다/날카롭다/답답하다
    "prior_treatment": {4182, 6556, 9525, 10596, 11990},  # 진단/수술/주사/재활/약
    "treatment_choice": {9525, 11990, 6556, 4182, 10596},  # 주사/약/수술/진단/재활
}


def _dynamic_evidence_min_score(agg: dict) -> float:
    """근거 인정 기준을 고정값 대신 이번 요청의 점수 분포(정확일치 제외, 상위 EVIDENCE_TOP_PERCENTILE)로
    정한다 - 질문마다 임베딩 유사도 분포가 달라 고정 임계값보다 안정적이다. [0.5, 0.9]로 범위를
    제한해 극단값(전부 통과/전부 탈락)을 막는다."""
    scores = sorted((r["score"] for r in agg.values() if not r["is_exact"]), reverse=True)
    if not scores:
        return RECOMMENDED_GLOSS_MIN_SCORE
    cutoff_idx = max(0, min(len(scores) - 1, int(len(scores) * EVIDENCE_TOP_PERCENTILE)))
    dynamic = scores[cutoff_idx]
    return max(RECOMMENDED_GLOSS_MIN_SCORE, min(dynamic, 0.9))


def _build_candidates(subcategory: str, answers_with_source: list, model_name: str):
    """답변 후보 여러 개의 키워드+표제어 매핑을 한 번에 만든다. 답변마다 대표 키워드(SpanTagger,
    subcategory 맥락 반영) 하나만 뽑는다. 표제어는 두 층위로 반환:
    (1) 답변 카드별 - 정확일치 여부 + "표현 가능한 글로스 없음" 판정만(유사도 전체 랭킹은
        카드 펼칠 때 /api/gloss/로 지연 요청 - 매번 전체를 채우면 응답이 너무 커짐)
    (2) 표제어 중심 집계 - 여러 답변의 키워드를 표제어(원문 인덱스) 기준으로 합친 뒤, 근거가 남은
        것(정확일치 또는 동적 임계값 이상)만 스코어순으로 반환. LLM 기반 시스템과 포맷을 맞춘
        압축형(compact_glosses)과 화면 표시용(table_rows) 두 벌로 낸다."""
    priority_glosses = SUBCATEGORY_GLOSS_PRIORITY.get(subcategory, set())
    priority_categories = SUBCATEGORY_CATEGORY_PRIORITY.get(subcategory, set())
    category_by_origin = gloss_category_by_origin()

    def _matches_priority_category(r: dict) -> bool:
        return category_by_origin.get(r["origin_number"]) in priority_categories

    t0 = time.perf_counter()
    answers = [a for a, _ in answers_with_source]
    tagged_per_answer = []  # answer_idx -> (keyword, confidence, span) | None
    for ans in answers:
        kw, conf, s, e = extract_keyword_learned(subcategory, ans)
        if kw:
            # extract_keyword_learned가 실제로 태깅한 위치를 그대로 쓴다(문자열 재검색 대신) - 같은
            # 단어가 답변에 두 번 나오면 재검색은 항상 첫 번째 위치를 잘못 잡을 수 있다.
            span = (s, e) if s is not None else None
            tagged_per_answer.append((kw, conf, span))
        else:
            tagged_per_answer.append(None)
    keyword_extract_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    flat_keywords = [tagged[0] for tagged in tagged_per_answer if tagged]
    flat_gloss_results = gloss_lookup_batch(
        flat_keywords, top_k=len(load_gloss_dict()), model_name=model_name,
    )
    gloss_by_answer_idx = {}
    cursor = 0
    for i, tagged in enumerate(tagged_per_answer):
        if tagged:
            gloss_by_answer_idx[i] = flat_gloss_results[cursor]
            cursor += 1

    # 두 패스로 나눈 이유: 1차로 row별 최고점을 먼저 확정해야 그 분포로 근거 인정 기준
    # (_dynamic_evidence_min_score)을 동적으로 정할 수 있고, 2차에서 그 기준을 넘는 것만 근거로 기록한다.
    agg: dict[int, dict] = {}  # origin_number -> {name, origin_number, score, is_exact}
    for gloss_pair in gloss_by_answer_idx.values():
        exact_hit, hits = gloss_pair
        entries = []
        if exact_hit:
            entries.append((exact_hit[0], exact_hit[1], exact_hit[2], True))
        entries += [(name, origin_number, score, False) for name, origin_number, score in hits]
        for name, origin_number, score, is_exact in entries:
            row = agg.get(origin_number)
            if row is None:
                agg[origin_number] = {
                    "name": name, "origin_number": origin_number, "score": score, "is_exact": is_exact,
                }
            elif score > row["score"]:
                row["name"], row["score"] = name, score
                row["is_exact"] = row["is_exact"] or is_exact

    evidence_min_score = _dynamic_evidence_min_score(agg)
    for row in agg.values():
        row["evidence"] = []
    for i, gloss_pair in gloss_by_answer_idx.items():
        exact_hit, hits = gloss_pair
        kw = tagged_per_answer[i][0]
        span = tagged_per_answer[i][2]
        entries = []
        if exact_hit:
            entries.append((exact_hit[0], exact_hit[1], exact_hit[2], True))
        entries += [(name, origin_number, score, False) for name, origin_number, score in hits]
        for name, origin_number, score, is_exact in entries:
            if not (is_exact or score >= evidence_min_score):
                continue
            row = agg[origin_number]
            evidence = {
                "answer_index": i, "keyword": kw, "score": score,
                "start": span[0] if span else None, "end": span[1] if span else None,
            }
            if evidence not in row["evidence"]:
                row["evidence"].append(evidence)
    for row in agg.values():
        row["evidence"].sort(key=lambda e: -e["score"])
    # 정렬: 정확일치 > 우선순위 묶음(표제어 > 카테고리 > 나머지) > 점수. 묶음 안에서는 점수를
    # 그대로 쓴다 - 점수를 구간으로 뭉개면 같은 묶음 안에서도 순서가 뒤집혀 보여 설명이 안 된다.
    recommended_glosses = sorted(
        agg.values(),
        key=lambda r: (
            -r["is_exact"],
            0 if r["origin_number"] in priority_glosses else 1 if _matches_priority_category(r) else 2,
            -r["score"],
        ),
    )

    candidates = []
    for i, ((ans, ans_src), tagged) in enumerate(zip(answers_with_source, tagged_per_answer)):
        kw_results = []
        if tagged:
            kw, conf, span = tagged
            exact_hit, hits = gloss_by_answer_idx[i]
            no_gloss = not exact_hit and (not hits or hits[0][2] < RECOMMENDED_GLOSS_MIN_SCORE)
            top_hit = exact_hit or (hits[0] if hits else None)
            kw_results.append({
                "keyword": kw, "confidence": conf,
                "start": span[0] if span else None, "end": span[1] if span else None,
                "no_gloss": no_gloss,
                "gloss_exact": (
                    {"name": exact_hit[0], "origin_number": exact_hit[1], "score": exact_hit[2]}
                    if exact_hit else None
                ),
                # 정확일치가 없어도 "키워드 -> 표제어_ID"를 보여줄 수 있게 1순위 후보를 같이 준다.
                "gloss_top": (
                    {"name": top_hit[0], "origin_number": top_hit[1], "score": round(top_hit[2], 4)}
                    if top_hit else None
                ),
            })
        candidates.append({"answer": ans, "answer_source": ans_src, "keywords": kw_results})
    gloss_ms = (time.perf_counter() - t0) * 1000

    # 점수 순서를 거슬러 앞당겨진 행 표시용 - 정렬 키가 점수보다 우선순위를 먼저 보기 때문에
    # 화면에서 순서가 뒤집혀 보이는 이유를 알려줘야 한다. 표제어 우선순위가 카테고리 우선순위보다
    # 정렬 키에서 앞서므로 둘 다 걸리면 gloss로 본다(같은 배지끼리의 역전까지 설명돼야 함).
    def _priority_kind(r: dict) -> str | None:
        if r["origin_number"] in priority_glosses:
            return "gloss"
        return "category" if _matches_priority_category(r) else None

    with_evidence = [r for r in recommended_glosses if r["evidence"]]
    shown = with_evidence[:RECOMMENDED_GLOSS_MAX_COUNT]

    # LLM 기반 시스템과 형식을 맞춘 압축 포맷. 답변 원문에서 실제로 검출된 키워드로 도달한 것만
    # 남기므로 source는 항상 answer_evidence - 스키마 호환을 위해 필드는 유지한다.
    compact_glosses = [
        {
            "keyword": r["name"],
            "glossId": r["origin_number"],
            "score": round(r["score"], 4),
            "source": "answer_evidence",
            "prioritized": _priority_kind(r) is not None,
            "priorityKind": _priority_kind(r),
        }
        for r in shown
    ]
    # 화면 표시용 - compact_glosses(API 스키마)는 그대로 두고 분류·근거 문장만 덧붙인다.
    # "의미 부류"(intentRole/intentLabel)는 LLM이 질문 의도를 해석해 붙이는 개념이라 넣지 않는다.
    table_rows = [
        {
            "keyword": r["name"],
            "glossId": r["origin_number"],
            "score": round(r["score"], 4),
            "category": category_by_origin.get(r["origin_number"], "기타"),
            "source": "answer_evidence",
            "prioritized": _priority_kind(r) is not None,
            "priorityKind": _priority_kind(r),
            "evidenceSentence": answers[r["evidence"][0]["answer_index"]],
            # 근거 문장 안에서 실제로 이 표제어를 뽑아낸 위치 - 프론트에서 <mark>로 강조 표시할 때 씀.
            "evidenceStart": r["evidence"][0]["start"],
            "evidenceEnd": r["evidence"][0]["end"],
        }
        for r in shown
    ]
    # "답변 매핑" 통계 - 채택된 표제어들이 실제로 어느 답변에서 나왔는지(answer_index) 세어
    # 답변 풀 중 몇 개가 표제어 산출에 기여했는지 본다.
    resolved_answer_idx = {e["answer_index"] for r in shown for e in r["evidence"]}
    # 문턱 미달 + 개수 제한에 밀린 것 = 화면에 안 나오는 전부.
    shown_origins = {r["origin_number"] for r in shown}
    excluded = [
        {
            "keyword": r["name"],
            "glossId": r["origin_number"],
            "score": round(r["score"], 4),
            "category": category_by_origin.get(r["origin_number"], "기타"),
        }
        for r in recommended_glosses
        if r["origin_number"] not in shown_origins
    ]
    stats = {
        "dropped_count": len(excluded),
        "answers_total": len(answers_with_source),
        "answers_resolved": len(resolved_answer_idx),
        "keyword_found": sum(1 for t in tagged_per_answer if t),
        "no_gloss_count": sum(1 for c in candidates for k in c["keywords"] if k["no_gloss"]),
        # 제외 목록은 사전 전체 규모(수백 개)라 컷오프에 가장 근접한 순으로 일부만 보낸다.
        "excluded_sample": sorted(excluded, key=lambda g: -g["score"])[:EXCLUDED_SAMPLE_SIZE],
    }
    return candidates, compact_glosses, table_rows, keyword_extract_ms, gloss_ms, evidence_min_score, stats


def _build_analysis(
    *, question, similarity_threshold, stage_results, sub_results, top3_subs,
    matched_stage, matched_subcategory, matched_question, matched_question_source,
    best_sim, retrieval_ok, used_filter, candidate_count, corpus_count,
    answers_with_source, gloss_stats, evidence_min_score, timings,
) -> dict:
    """추천 근거 분석 화면 전용 뷰 - 파이프라인이 이미 계산한 중간값을 모아 담기만 한다(재계산 없음).
    LLM 전용 개념(의도 확장, 답변 생성 latency, provider 설정)은 우리 구조에 없어 담지 않는다."""
    classify_ms, retrieve_ms, keyword_extract_ms, gloss_ms, total_ms = timings
    top_stage, top_stage_p = stage_results[0]
    top_sub, top_sub_p = sub_results[0]
    sub_margin = top_sub_p - (sub_results[1][1] if len(sub_results) > 1 else 0.0)

    source_counts: dict[str, int] = {}
    for _, src in answers_with_source:
        source_counts[src] = source_counts.get(src, 0) + 1

    scope = f"세부분류 상위 3개로 후보 축소({candidate_count}/{corpus_count}건 비교)" if used_filter \
        else f"후보 부족으로 필터 해제, 코퍼스 전체 {corpus_count}건 비교"
    if matched_question:
        verdict = "임계값 통과" if retrieval_ok else f"임계값 {similarity_threshold:.2f} 미달"
        reason = (f"기존 질문 pool 매칭: '{matched_question}' "
                  f"(유사도 {best_sim:.3f}, margin {sub_margin:.2f}, {verdict}) · {scope}")
    else:
        reason = "매칭된 기존 질문 없음"

    return {
        "classification": {
            "question": question,
            "predictedStage": top_stage,
            "predictedStageProb": round(top_stage_p, 4),
            "predictedSub": top_sub,
            "predictedSubProb": round(top_sub_p, 4),
            "usedStage": matched_stage,
            "usedSub": matched_subcategory,
            "subMargin": round(sub_margin, 4),
            "searchedSubs": top3_subs,
            "path": "classifier+retrieval",
            "reason": reason,
            "latencyMs": round(classify_ms, 1),
        },
        "retrieval": {
            "matchedQuestion": matched_question,
            "matchedQuestionSource": matched_question_source,
            "similarity": round(best_sim, 4),
            "similarityThreshold": similarity_threshold,
            "retrievalOk": retrieval_ok,
            "usedFilter": used_filter,
            "candidateCount": candidate_count,
            "corpusCount": corpus_count,
            "latencyMs": round(retrieve_ms, 1),
        },
        "answerPool": {
            "total": len(answers_with_source),
            "keywordFound": gloss_stats["keyword_found"],
            "noGlossCount": gloss_stats["no_gloss_count"],
            "resolved": gloss_stats["answers_resolved"],
            "sources": [
                {"source": s, "count": n}
                for s, n in sorted(source_counts.items(), key=lambda x: -x[1])
            ],
            "latencyMs": round(keyword_extract_ms, 1),
        },
        "cutoff": {
            "minScore": round(evidence_min_score, 3),
            "topPercentile": EVIDENCE_TOP_PERCENTILE,
            "maxCount": RECOMMENDED_GLOSS_MAX_COUNT,
            "excludedCount": gloss_stats["dropped_count"],
            "excludedSample": gloss_stats["excluded_sample"],
            "latencyMs": round(gloss_ms, 1),
        },
        "latency": {
            "classifyMs": round(classify_ms, 1),
            "retrieveMs": round(retrieve_ms, 1),
            "keywordExtractMs": round(keyword_extract_ms, 1),
            "glossScoringMs": round(gloss_ms, 1),
            "totalMs": round(total_ms, 1),
        },
    }


def run_pipeline(question: str, emb_model, similarity_threshold: float) -> dict:
    """메인 플로우(질문 -> 분류 -> 검색 -> 키워드 -> 표제어)를 한 번에 실행한다. 단계별 소요시간과
    콜드스타트 여부(lru_cache 미스 발생 시 모델 로딩 포함)도 같이 반환한다. LLM 생성 폴백은 없다 -
    검색이 임계값 미달이면 "비슷한 기존 질문을 찾지 못했다"는 사실을 그대로 보여준다.
    표제어 반환 형태는 _build_candidates 참고."""
    t_start = time.perf_counter()
    misses_before = _total_cache_misses()
    model_name = _resolve_model(emb_model)

    t0 = time.perf_counter()
    stage_results, sub_results = predict(question)
    ground_truth = ground_truth_labels(question, model_name)
    classify_ms = (time.perf_counter() - t0) * 1000
    top_stage, top_stage_p = stage_results[0]
    top_sub, top_sub_p = sub_results[0]
    top3_subs = [label for label, _ in sub_results[:3]]

    # 검색은 항상 계산한다(24ms 정도로 저렴하고, 임계값 판정에도 필요).
    t0 = time.perf_counter()
    matches, used_filter = retrieve_answer(
        question, top3_subs, top_k=1, max_examples=20, model_name=model_name,
    )
    best_sim = matches[0]["similarity"] if matches else 0.0
    retrieval_raw = [(ex["answer"], ex["source"]) for ex in matches[0]["examples"]] if matches else []
    matched_question = matches[0]["matched_question"] if matches else None
    matched_question_source = matches[0]["matched_question_source"] if matches else None
    # 매칭이 top3_subs 중 2·3위에서 왔을 수 있어 top_sub 대신 실제 매칭된 세부분류를 쓴다
    matched_subcategory = matches[0]["matched_subcategory"] if matches else top_sub
    matched_stage = matches[0]["matched_stage"] if matches else top_stage
    candidate_count = matches[0]["candidate_count"] if matches else 0
    corpus_count = matches[0]["corpus_count"] if matches else 0
    retrieve_ms = (time.perf_counter() - t0) * 1000

    retrieval_ok = bool(matches) and best_sim >= similarity_threshold

    if retrieval_raw:
        retrieval_candidates, recommended_glosses, table_rows, keyword_extract_ms, gloss_ms, evidence_min_score, gloss_stats = _build_candidates(
            matched_subcategory, retrieval_raw, model_name
        )
    else:
        retrieval_candidates, recommended_glosses, table_rows, keyword_extract_ms, gloss_ms = [], [], [], 0.0, 0.0
        evidence_min_score = RECOMMENDED_GLOSS_MIN_SCORE
        gloss_stats = {
            "dropped_count": 0, "answers_total": 0, "answers_resolved": 0,
            "keyword_found": 0, "no_gloss_count": 0, "excluded_sample": [],
        }

    total_ms = (time.perf_counter() - t_start) * 1000
    cold_start = _total_cache_misses() > misses_before

    # 남은 표제어는 전부 답변 근거 기반 - 의도 확장(LLM 개념)은 만들지 않으므로 항상 0.
    evidence_count = len(recommended_glosses)
    stats = {
        "final_count": len(recommended_glosses),
        "evidence_count": evidence_count,
        "expansion_count": 0,
        "dropped_count": gloss_stats["dropped_count"],
        "answers_total": gloss_stats["answers_total"],
        "answers_resolved": gloss_stats["answers_resolved"],
        "total_ms": round(total_ms, 1),
    }

    analysis = _build_analysis(
        question=question, similarity_threshold=similarity_threshold,
        stage_results=stage_results, sub_results=sub_results, top3_subs=top3_subs,
        matched_stage=matched_stage, matched_subcategory=matched_subcategory,
        matched_question=matched_question, matched_question_source=matched_question_source,
        best_sim=best_sim, retrieval_ok=retrieval_ok, used_filter=used_filter,
        candidate_count=candidate_count, corpus_count=corpus_count,
        answers_with_source=retrieval_raw, gloss_stats=gloss_stats,
        evidence_min_score=evidence_min_score,
        timings=(classify_ms, retrieve_ms, keyword_extract_ms, gloss_ms, total_ms),
    )

    return {
        "stage_results": [{"label": l, "prob": p} for l, p in stage_results],
        "sub_results": [{"label": l, "prob": p} for l, p in sub_results],
        "top_stage": {"label": top_stage, "prob": top_stage_p},
        "top_sub": {"label": top_sub, "prob": top_sub_p},
        "retrieval_ok": retrieval_ok,
        "similarity": best_sim,
        "used_filter": used_filter,
        "matched_question": matched_question,
        "matched_question_source": matched_question_source,
        "retrieval_candidates": retrieval_candidates,
        "recommended_glosses": recommended_glosses,
        "table_rows": table_rows,
        "evidence_min_score": round(evidence_min_score, 3),
        "stats": stats,
        "analysis": analysis,
        # LLM 기반 시스템과 같은 응답 봉투 - output/tuples/pairs/idPairs는 같은 keywords를 키 조합만
        # 바꿔 다시 인코딩한 편의 뷰다(다운스트림이 어떤 형태를 쓰든 그대로 받게).
        "keywords_envelope": {
            "question": question,
            "stage": top_stage,
            "subCategory": matched_subcategory,
            "count": len(recommended_glosses),
            "keywords": recommended_glosses,
            "output": [[f"{g['keyword']}_{g['glossId']}", g['score']] for g in recommended_glosses],
            "tuples": [[g['glossId'], g['keyword'], g['score']] for g in recommended_glosses],
            "pairs": [[g['keyword'], g['score']] for g in recommended_glosses],
            "idPairs": [[g['glossId'], g['score']] for g in recommended_glosses],
        },
        "ground_truth": ground_truth,
        "emb_model_used": {"model_id": model_name, "label": _model_label(model_name)},
        "timing": {
            "classify_ms": round(classify_ms, 1),
            "retrieve_ms": round(retrieve_ms, 1),
            "keyword_extract_ms": round(keyword_extract_ms, 1),
            "gloss_ms": round(gloss_ms, 1),
            "total_ms": round(total_ms, 1),
            "cold_start": cold_start,
        },
    }


def embedding_model_options() -> dict:
    return {
        "options": [
            {
                "rank": i + 1, "label": label, "model_id": model_id, "is_default": model_id == EMB_MODEL_NAME,
                "loaded": is_embedder_loaded(model_id),
            }
            for i, (label, model_id) in enumerate(EMB_MODEL_OPTIONS.items())
        ],
        "default_model_id": EMB_MODEL_NAME,
    }


def gloss_dictionary() -> dict:
    """표제어 사전 전체를 표(인덱스·이름·분류) + 통계로 반환한다. 세부분류별 매핑은 고정 매핑이
    아니라 질문마다 즉석 임베딩 검색이라 여기 없다."""
    df = load_gloss_dict()
    glosses = [
        {
            "origin_number": int(row["Origin_Number"]), "name": str(row["Gloss_Name"]),
            "category": str(row["Gloss_Category"]),
        }
        for _, row in df.iterrows()
    ]
    glosses.sort(key=lambda g: g["origin_number"])
    category_counts: dict[str, int] = {}
    for g in glosses:
        category_counts[g["category"]] = category_counts.get(g["category"], 0) + 1
    categories = sorted(
        ({"category": c, "count": n} for c, n in category_counts.items()),
        key=lambda x: -x["count"],
    )
    return {"total": len(glosses), "categories": categories, "glosses": glosses}


def dataset_stats() -> list:
    return compute_dataset_stats().to_dict(orient="records")


def subcategory_stats() -> list:
    return compute_subcategory_stats().to_dict(orient="records")


def label_lists() -> dict:
    """분류기가 예측 가능한 문진 단계·세부분류 전체 목록(모델이 학습 때 실제로 본 라벨셋)과
    단계->세부분류 그룹핑을 반환한다. 그룹핑은 predict()가 계층 제약에 쓰는 것과 같은
    app.models.classifier.stage_to_subcategories()를 그대로 재사용한다(중복 구현 없음)."""
    _, _, id2stage, id2sub, _ = _load_classifier_model()
    stages = sorted(id2stage.values())
    subs = sorted(id2sub.values())

    grouped = {
        stage: sorted(s & set(subs)) for stage, s in _stage_to_subcategories().items()
    }
    return {
        "stages": stages,
        "subcategories": subs,
        "stage_to_subcategories": {stage: grouped.get(stage, []) for stage in stages},
    }


def example_questions(n: int = 5) -> list:
    """의사 질문 예시 n개를 무작위로 뽑는다(프론트의 '예시 눌러보기' 버튼용)."""
    questions_df, _, _ = load_corpus()
    pool = questions_df["의사 질문(개별)"].dropna().astype(str).unique().tolist()
    pool = [q for q in pool if 4 <= len(q) <= 40]
    return random.sample(pool, min(n, len(pool)))
