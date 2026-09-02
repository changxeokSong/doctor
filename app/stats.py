"""RAG 코퍼스의 단계별 질문/답변 통계(기존 vs LLM 증강 구분)를 계산한다.
데모 사이드바에 '데이터셋 현황'으로 표시하기 위한 용도."""
from functools import lru_cache

import pandas as pd

from app.config import (
    CORPUS_EXCEL, ORIGINAL_QUESTION_SOURCES, ORIGINAL_ANSWER_SOURCES, SUBCATEGORY_SEMANTIC_ROLES,
)

_STAGE_ORDER = [
    "진료개시", "통증 부위", "통증강도", "통증 발생시점", "통증 양상", "통증 유발/완화 요인",
    "통증 동반증상", "통증 시간대/상황별 변화", "통증 지속성/패턴", "과거질환", "약물복용",
    "알레르기 및 약물반응", "생활습관", "수술 및 입원 이력", "치료 방향 설명 및 선택 제안",
]


@lru_cache(maxsize=None)
def compute_dataset_stats() -> pd.DataFrame:
    q = pd.read_excel(CORPUS_EXCEL, sheet_name="의사질문_목록")
    a = pd.read_excel(CORPUS_EXCEL, sheet_name="확장문진_답변키워드")

    is_orig = q["질문출처"].isin(ORIGINAL_QUESTION_SOURCES)
    qid2stage = dict(zip(q["의사질문ID"], q["단계"]))
    a = a.copy()
    a["단계"] = a["의사질문ID"].map(qid2stage)
    # 답변의 기존/증강은 부모 질문이 아니라 답변 자신의 출처로 판정한다 - 원본 질문에 달린
    # 증강 답변(34건)이 있어, 질문 출처로 세면 검색 코퍼스(retriever)와 수치가 어긋난다.
    is_orig_answer = a["답변출처"].isin(ORIGINAL_ANSWER_SOURCES)

    g_q_orig = q[is_orig].groupby("단계").size()
    g_q_aug = q[~is_orig].groupby("단계").size()
    g_a_orig = a[is_orig_answer].groupby("단계").size()
    g_a_aug = a[~is_orig_answer].groupby("단계").size()

    stages = [s for s in _STAGE_ORDER if s in set(q["단계"])]
    stages += [s for s in q["단계"].drop_duplicates() if s not in stages]

    rows = []
    for s in stages:
        rows.append({
            "단계": s,
            "질문(기존)": int(g_q_orig.get(s, 0)),
            "질문(증강)": int(g_q_aug.get(s, 0)),
            "질문 합계": int(g_q_orig.get(s, 0) + g_q_aug.get(s, 0)),
            "답변(기존)": int(g_a_orig.get(s, 0)),
            "답변(증강)": int(g_a_aug.get(s, 0)),
            "답변 합계": int(g_a_orig.get(s, 0) + g_a_aug.get(s, 0)),
        })
    df = pd.DataFrame(rows)
    total = {
        "단계": "합계",
        "질문(기존)": df["질문(기존)"].sum(), "질문(증강)": df["질문(증강)"].sum(), "질문 합계": df["질문 합계"].sum(),
        "답변(기존)": df["답변(기존)"].sum(), "답변(증강)": df["답변(증강)"].sum(), "답변 합계": df["답변 합계"].sum(),
    }
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


@lru_cache(maxsize=None)
def compute_subcategory_stats() -> pd.DataFrame:
    """단계·세부분류 조합별 질문/답변 개수. 같은 세부분류 이름이 여러 단계에서 재사용되므로
    (예: "lifestyle"이 생활습관/수술 및 입원 이력 둘 다에 있음) 반드시 (단계, 세부분류) 쌍으로 묶는다.
    집계 대상은 retriever.load_corpus()와 같은 원본만 - 화면에 실제 검색 코퍼스 규모가 보여야 한다."""
    q = pd.read_excel(CORPUS_EXCEL, sheet_name="의사질문_목록")
    a = pd.read_excel(CORPUS_EXCEL, sheet_name="확장문진_답변키워드")

    q = q[q["질문출처"].isin(ORIGINAL_QUESTION_SOURCES)]
    a = a[a["답변출처"].isin(ORIGINAL_ANSWER_SOURCES)].copy()
    qid2stage = dict(zip(q["의사질문ID"], q["단계"]))
    qid2sub = dict(zip(q["의사질문ID"], q["세부분류"]))
    a["단계"] = a["의사질문ID"].map(qid2stage)
    a["세부분류"] = a["의사질문ID"].map(qid2sub)

    g_q = q.groupby(["단계", "세부분류"]).size()
    g_a = a.groupby(["단계", "세부분류"]).size()
    pairs = sorted(set(g_q.index) | set(g_a.index))

    default_roles = {"primary": "-", "secondary": []}
    rows = [
        {
            "단계": stage, "세부분류": sub,
            "질문": int(g_q.get((stage, sub), 0)), "답변": int(g_a.get((stage, sub), 0)),
            "primary_role": SUBCATEGORY_SEMANTIC_ROLES.get((stage, sub), default_roles)["primary"],
            "secondary_roles": list(
                SUBCATEGORY_SEMANTIC_ROLES.get((stage, sub), default_roles)["secondary"]
            ),
        }
        for stage, sub in pairs
    ]
    return pd.DataFrame(rows)
