"""임베딩 + DB 검색(생성이 없는 순수 검색이라 'RAG'가 아님):
의사 질문을 임베딩해 코퍼스 질문들과 유사도 비교, 가장 비슷한 질문에 달린 실제 환자 답변을 가져온다.

근접중복 질문(표현은 다르지만 실질적으로 같은 질문)은 행을 지우지 않는다 — 각 표현을 검색 후보로
남겨야 그 말투로 검색했을 때도 매칭되기 때문. 대신 '그룹대표ID'로 묶어두고, 답변 예시를 보여줄
때만 그룹 전체의 답변 풀을 합쳐서 준다."""
import os
from functools import lru_cache

import numpy as np
import pandas as pd

from app.config import CORPUS_EXCEL, EMB_MODEL_NAME, MIN_CANDIDATES_FOR_FILTER
from app.embedding import load_embedder, cache_suffix, prep_query, prep_passage


@lru_cache(maxsize=None)
def load_corpus(model_name: str = EMB_MODEL_NAME):
    questions_df = pd.read_excel(CORPUS_EXCEL, sheet_name="의사질문_목록")
    answers_df = pd.read_excel(CORPUS_EXCEL, sheet_name="확장문진_답변키워드")

    if "그룹대표ID" not in questions_df.columns:
        questions_df["그룹대표ID"] = questions_df["의사질문ID"]
    qid_to_group = dict(zip(questions_df["의사질문ID"], questions_df["그룹대표ID"]))
    answers_df = answers_df.copy()
    answers_df["그룹대표ID"] = answers_df["의사질문ID"].map(qid_to_group)

    # 그룹 전체(자기 자신 + 근접중복 멤버들)의 답변 풀 — 매칭된 질문이 어느 멤버든 이걸로 조회한다.
    # 답변출처(원본/증강 구분)도 같이 들고 다녀서, 화면에 이 답변이 기존 데이터인지 LLM 증강인지 보여준다.
    answers_by_group = {
        group_id: g[["환자 답변", "대표 환자키워드(답변 중 원문)", "답변출처"]].values.tolist()
        for group_id, g in answers_df.groupby("그룹대표ID")
    }

    embedder = load_embedder(model_name)
    cache_path = f"./cache/corpus_question_embeddings__{cache_suffix(model_name)}.npy"
    if os.path.exists(cache_path):
        question_embeddings = np.load(cache_path)
    else:
        question_embeddings = embedder.encode(
            prep_passage(model_name, questions_df["의사 질문(개별)"].tolist()), normalize_embeddings=True
        )
        np.save(cache_path, question_embeddings)
    return questions_df, answers_by_group, question_embeddings


def ground_truth_labels(question: str, model_name: str = EMB_MODEL_NAME) -> dict | None:
    """입력 질문이 코퍼스에 있는 기존 질문과 글자 그대로 정확히 일치하면(예시 버튼으로 눌렀을 때 등)
    그 질문에 실제로 붙어있는 정답 라벨(단계/세부분류)을 돌려준다. 임베딩 유사도가 아니라 완전
    문자열 일치만 본다 - 자유롭게 타이핑한 새 질문은 정답이 없으니 None."""
    questions_df, _, _ = load_corpus(model_name)
    hit = questions_df[questions_df["의사 질문(개별)"] == question]
    if hit.empty:
        return None
    row = hit.iloc[0]
    return {"stage": row["단계"], "subcategory": row["세부분류"]}


def retrieve_answer(
    question: str, predicted_subcategories, top_k: int = 1, max_examples: int = 20,
    model_name: str = EMB_MODEL_NAME,
):
    """predicted_subcategories: 세부분류 문자열 1개 또는 리스트(상위 후보 여러 개).

    분류기 예측 1위 세부분류에만 검색을 가두면, 1위·2위 확률 차이가 근소해 실제로는 2위가 맞는
    질문을 검색 후보에서 아예 놓칠 수 있다. 그래서 상위 후보 여러 개(예: top-3)를 한꺼번에
    검색 대상에 포함할 수 있게 한다."""
    questions_df, answers_by_group, question_embeddings = load_corpus(model_name)
    embedder = load_embedder(model_name)

    if isinstance(predicted_subcategories, str):
        predicted_subcategories = [predicted_subcategories]

    mask = questions_df["세부분류"].isin(predicted_subcategories).values
    used_filter = True
    if mask.sum() < MIN_CANDIDATES_FOR_FILTER:
        mask = np.ones(len(questions_df), dtype=bool)
        used_filter = False

    cand_idx = np.where(mask)[0]
    cand_emb = question_embeddings[cand_idx]
    q_emb = embedder.encode(prep_query(model_name, [question]), normalize_embeddings=True)[0]
    sims = cand_emb @ q_emb
    order = np.argsort(-sims)[:top_k]
    top_idx = cand_idx[order]
    top_sims = sims[order]

    results = []
    for idx, sim in zip(top_idx, top_sims):
        row = questions_df.iloc[idx]
        examples = answers_by_group.get(row["그룹대표ID"], [])
        results.append({
            "matched_question": row["의사 질문(개별)"],
            "matched_question_source": row["질문출처"],
            "matched_stage": row["단계"],
            "matched_subcategory": row["세부분류"],
            "similarity": float(sim),
            "examples": [
                {"answer": a, "keyword": k, "source": s} for a, k, s in examples[:max_examples]
            ],
        })
    return results, used_filter
