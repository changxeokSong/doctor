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
from app.nlp.morphology import get_kiwi, has_noun
from app.retrieval.gloss import (
    gloss_lookup_batch, load_gloss_dict, build_exact_gloss_index, build_gloss_synonym_embeddings,
)
from app.retrieval.retriever import retrieve_answer, load_corpus, ground_truth_labels
from app.stats import compute_dataset_stats

# lru_cache로 감싼 모델/리소스 로더들 - .cache_info().misses가 늘었으면 이번 요청에서 뭔가
# 새로 로드됐다는 뜻이라, "이번 응답에 모델 로딩 시간이 포함됐는지"를 판단하는 데 쓴다.
_LOADERS = [
    _load_classifier_model, _stage_to_subcategories, load_embedder,
    load_gloss_dict, build_exact_gloss_index, build_gloss_synonym_embeddings,
    get_kiwi, load_corpus, load_keyword_model,
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
    """입력(세부분류, 환자 답변) -> 출력(대표 키워드 1개 + 신뢰도)만 반환하는 단순 계약.
    v4(kiwi 형태소분석, 답변 내용어 전체를 다 뽑던 방식)는 2026-08-19(진하형 피드백)에 완전히 뺐다 -
    "무릎이 아파서 왔어요"에 무릎/아프다/오다가 다 나오면 후속 모듈이 모든 경우의 수를 다 고려해야
    해서 비효율적이라는 지적. SpanTagger(v2)가 세부분류 맥락을 반영해 무릎처럼 정보량 있는 표현 하나만
    고른다."""
    keyword, confidence = extract_keyword_learned(subcategory, answer)
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


# 집계 표(recommended_glosses)는 컷 없이 사전 전체(~654개)를 스코어순으로 다 보여준다(2026-08-19,
# 사용자가 직접 순위를 보고 판단하길 원함 — "아침에 일어날 때"처럼 긴 조건절 키워드에서 SAP-BERT-Ko-En이
# 완전 무관한 단어를 고스코어로 내는 걸 한 번 확인했지만, 순위 컬럼을 붙여서 사용자가 스스로 거르게
# 한다). 카드별 "표현 가능한 글로스 없음" 판정에는 여전히 이 고정값을 쓴다(그 답변 자체 하나에 대한
# 판단이라 분포 계산이 무의미함). "근거(evidence)로 인정할지"는 아래 _dynamic_evidence_min_score가
# 정하는 동적 값을 쓴다(2026-08-26, 사용자 요청).
RECOMMENDED_GLOSS_MIN_SCORE = 0.5


EVIDENCE_TOP_PERCENTILE = 0.15  # 상위 15%만 "근거 있음"으로 인정한다(2026-08-26 - 30%로 한 번
# 올려봤다가 표제어가 202개까지 늘어 다시 노이즈가 는 걸 보고 15%로 되돌림).


def _dynamic_evidence_min_score(agg: dict) -> float:
    """근거 인정 기준을 고정값 대신 이번 요청의 점수 분포로 정한다 - 질문마다 임베딩 유사도 분포
    자체가 다를 수 있어서(예: 흔한 단어가 많이 섞인 답변은 전체적으로 점수가 낮게 나옴), 고정
    0.5보다 "이번 요청 기준으로 확실히 높은 축"을 근거로 인정하는 게 더 안정적이다(2026-08-26,
    사용자 요청 - "평균 임계값 확인해서 동적으로 정할 수 있냐").

    처음엔 평균+표준편차로 계산했는데(mean+stdev), 사용자가 "이게 좋은 기준인지 모르겠다"고
    재고해서 실측 비교함: 실제 데이터(648개 점수, 평균 0.505·표준편차 0.061)로는 mean+stdev가
    상위 14%(92/648)를 통과시켰다 - 나쁘지 않지만, 표준편차가 질문마다 얼마나 넓거나 좁을지
    예측할 수 없어서 "몇 %가 통과할지"가 질문마다 들쭉날쭉해질 수 있다는 게 문제였다. 그래서
    상위 퍼센타일(EVIDENCE_TOP_PERCENTILE) 방식으로 바꿨다 - "항상 상위 15%만 보여준다"가
    더 예측 가능하고 설명하기도 쉽다(2026-08-26). 정확일치는 이미 1.0 근처에 몰려 분포를
    왜곡하니 제외하고 계산한다. 위아래로는 [0.5, 0.9] 범위로 잘라서 극단값(전부 다 뜨거나
    하나도 안 뜨는 경우)을 막는다."""
    scores = sorted((r["score"] for r in agg.values() if not r["is_exact"]), reverse=True)
    if not scores:
        return RECOMMENDED_GLOSS_MIN_SCORE
    cutoff_idx = max(0, min(len(scores) - 1, int(len(scores) * EVIDENCE_TOP_PERCENTILE)))
    dynamic = scores[cutoff_idx]
    return max(RECOMMENDED_GLOSS_MIN_SCORE, min(dynamic, 0.9))


def _build_candidates(subcategory: str, answers_with_source: list, model_name: str):
    """답변 후보 여러 개의 키워드+표제어 매핑을 한 번에 만든다. 답변마다 대표 키워드 학습 모델
    (SpanTagger, subcategory 맥락 반영, 질문에 이미 내포된 서술어는 제외) 하나만 낸다 —
    2026-08-19(진하형 피드백)에 형태소분석(kiwi, 내용어 전체) 방식과 나란히 비교해본 뒤 이 방식만으로
    충분하다고 판단해 형태소분석 폴백까지 완전히 뺐다. 빈 문자열(초단문 답변 등,
    try_v2_keyword_extractor_20260819.py 오답 샘플 참고)이면 그 답변엔 키워드가 없는 채로 나간다.

    표제어는 두 층위로 반환한다:
    (1) 답변 카드별 - 정확일치 여부 + "표현 가능한 글로스 없음" 판정만. 유사도 랭킹 전체(654개)는
        카드를 펼칠 때 프론트가 /api/gloss/로 따로 지연 요청한다(답변마다 미리 다 채워 응답이
        ~900KB까지 커져 서버 디스크를 채운 장애 이후 변경, 2026-08-19).
    (2) 표제어 중심 집계(recommended_glosses) - 답변 여러 개에 흩어진 키워드를 표제어(원문 인덱스)
        기준으로 합쳐서, 어느 답변의 어느 키워드가 근거인지와 함께 사전 전체(654개)를 스코어순으로
        반환한다(진하형이 공유한 "표제어 중심 집계 + 근거 표시" 포맷 참고, 2026-08-19 — 그 포맷의
        LLM 생성·의도 확장 부분은 뺐고, "품질 컷"도 우선 빼고 전체를 다 보여주는 쪽으로 바꿨다 —
        사용자가 컷 없이 전체를 먼저 보길 원함)."""
    t0 = time.perf_counter()
    answers = [a for a, _ in answers_with_source]
    tagged_per_answer = []  # answer_idx -> (keyword, confidence, span) | None
    for ans in answers:
        kw, conf = extract_keyword_learned(subcategory, ans)
        if kw:
            idx = ans.find(kw)
            span = (idx, idx + len(kw)) if idx != -1 else None
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

    # top_k가 사전 전체 크기라 모든 키워드가 모든 표제어에 대해 어떤 점수든 갖는다 - 그래서 두 번
    # 훑는다. 1차: row별 최고점(score)만 먼저 확정 - 이 최고점 분포로 "근거로 인정할 기준"을 동적으로
    # 정한다(_dynamic_evidence_min_score). 2차: 그 기준을 넘는 항목만 근거(evidence)로 기록한다 -
    # 안 그러면 무관한 답변까지 "근거"로 뜬다(예: "허리"가 "심장" 표제어의 근거로 딸려오는 식,
    # 2026-08-19 확인). 두 패스로 나눈 이유는 "이번 요청 점수 분포"를 알아야 기준을 정할 수 있는데,
    # 그 분포 자체가 전체 항목을 다 훑어야 나오기 때문(2026-08-26).
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
        entries = []
        if exact_hit:
            entries.append((exact_hit[0], exact_hit[1], exact_hit[2], True))
        entries += [(name, origin_number, score, False) for name, origin_number, score in hits]
        for name, origin_number, score, is_exact in entries:
            if not (is_exact or score >= evidence_min_score):
                continue
            row = agg[origin_number]
            evidence = {"answer_index": i, "keyword": kw, "score": score}
            if evidence not in row["evidence"]:
                row["evidence"].append(evidence)
    # 근거 목록 안에서도 가장 유사도 높은(가까운) 답변이 맨 위로 오도록 정렬한다(2026-08-19, 사용자
    # 요청 - 표에서 "답변2, 답변3, 답변4..." 처리 순서가 아니라 실제로 제일 가까운 게 먼저 보이길 원함).
    for row in agg.values():
        row["evidence"].sort(key=lambda e: -e["score"])
    # 정렬은 여전히 점수가 1순위다 - 다만 점수를 0.01 단위로 반올림해서 "사실상 같은 점수"인
    # 표제어끼리는 명사(무엇이 - 신체부위 등)를 형용사/동사(어떻다 - 아프다 등)보다 앞세운다
    # (2026-08-26, 사용자 요청 - "점수 우선, 명사는 근소한 차이일 때만"이라고 미리 합의했던 걸
    # 이번에 실제로 구현함). has_noun은 kiwi 품사 태그 기반이라 하드코딩 단어 목록이 아니다.
    recommended_glosses = sorted(
        agg.values(),
        key=lambda r: (-r["is_exact"], -round(r["score"], 2), not has_noun(r["name"])),
    )

    candidates = []
    for i, ((ans, ans_src), tagged) in enumerate(zip(answers_with_source, tagged_per_answer)):
        kw_results = []
        if tagged:
            kw, conf, span = tagged
            exact_hit, hits = gloss_by_answer_idx[i]
            no_gloss = not exact_hit and (not hits or hits[0][2] < RECOMMENDED_GLOSS_MIN_SCORE)
            kw_results.append({
                "keyword": kw, "confidence": conf,
                "start": span[0] if span else None, "end": span[1] if span else None,
                "no_gloss": no_gloss,
                "gloss_exact": (
                    {"name": exact_hit[0], "origin_number": exact_hit[1], "score": exact_hit[2]}
                    if exact_hit else None
                ),
            })
        candidates.append({"answer": ans, "answer_source": ans_src, "keywords": kw_results})
    gloss_ms = (time.perf_counter() - t0) * 1000
    return candidates, recommended_glosses, keyword_extract_ms, gloss_ms, evidence_min_score


def run_pipeline(question: str, emb_model, similarity_threshold: float) -> dict:
    """demo_app.py의 메인 플로우(질문 -> 분류 -> 검색 -> 키워드 -> 표제어)를 한 번에 실행한다.
    단계별 소요시간(ms)과, 이번 요청에서 모델을 새로 로드했는지(cold start)도 같이 반환한다 —
    처음 실행되면 lru_cache가 비어있어서 모델 로딩 시간까지 그 단계 시간에 포함된다.
    키워드 추출은 대표 키워드 1개(세부분류 맥락 반영, SpanTagger) — 2026-08-19 진하형 피드백으로
    재도입, _build_candidates 참고. 표제어는 답변 카드별로는 정확일치 여부만 넣고(유사도 전체 랭킹은
    프론트가 카드를 펼칠 때 /api/gloss/로 따로 지연 로딩, 매번 전체를 미리 계산해 넣었다가 응답이
    커져서 서버 디스크를 채운 장애 이후 변경) + 별도로 `recommended_glosses`에 답변 전체를 표제어
    기준으로 합친 집계(컷 없이 전체, 근거 표시)를 반환한다 — _build_candidates 참고. 검색이
    임계값 미달이어도 KoBART 생성 폴백은 더 없다 —
    2026-07-25(ISSUE-64)에 코드·모델 자체를 삭제했다(반복생성 등 품질 문제가 있었고, "지금 코퍼스에
    없는 질문"이라는 사실을 정직하게 보여주는 편이 낫다는 판단). retrieval_ok가 False면 프론트가
    "비슷한 기존 질문을 찾지 못했다"는 걸 그대로 보여준다. 답변 소스가 검색(retriever) 하나뿐이라
    show_retrieval 같은 on/off 파라미터도 같이(ISSUE-64) 없앴다 — 항상 계산해서 보여준다."""
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
    retrieve_ms = (time.perf_counter() - t0) * 1000

    retrieval_ok = bool(matches) and best_sim >= similarity_threshold

    if retrieval_raw:
        retrieval_candidates, recommended_glosses, keyword_extract_ms, gloss_ms, evidence_min_score = _build_candidates(
            top_sub, retrieval_raw, model_name
        )
    else:
        retrieval_candidates, recommended_glosses, keyword_extract_ms, gloss_ms = [], [], 0.0, 0.0
        evidence_min_score = RECOMMENDED_GLOSS_MIN_SCORE

    total_ms = (time.perf_counter() - t_start) * 1000
    cold_start = _total_cache_misses() > misses_before

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
        "evidence_min_score": round(evidence_min_score, 3),
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
    """표제어 사전 전체를 표(인덱스·이름·분류) + 통계로 반환한다(2026-08-26, 사용자 요청 -
    조윤기 팀이 회의에서 "이 단어가 왜 없냐"는 질문에 대답 못한 걸 보고, 우리도 사전 전체를
    투명하게 보여주는 페이지가 있으면 좋겠다고 판단함). 세부분류별 매핑(어느 세부분류에 어떤
    글로스가 뜨는지)은 우리 아키텍처가 고정 매핑이 아니라 질문마다 즉석 임베딩 검색이라 이
    함수에는 없다 - 필요해지면 별도 배치 계산으로 붙여야 한다."""
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
