"""RAG 코퍼스의 단계별 질문/답변 통계(기존 vs LLM 증강 구분)를 계산한다.
데모 사이드바에 '데이터셋 현황'으로 표시하기 위한 용도."""
from functools import lru_cache

import pandas as pd

from app.config import CORPUS_EXCEL

_ORIGINAL_SOURCES = {"추가문진", "기존분리"}

_STAGE_ORDER = [
    "진료개시", "통증 부위", "통증강도", "통증 발생시점", "통증 양상", "통증 유발/완화 요인",
    "통증 동반증상", "통증 시간대/상황별 변화", "통증 지속성/패턴", "과거질환", "약물복용",
    "알레르기 및 약물반응", "생활습관", "수술 및 입원 이력", "치료 방향 설명 및 선택 제안",
]


@lru_cache(maxsize=None)
def compute_dataset_stats() -> pd.DataFrame:
    q = pd.read_excel(CORPUS_EXCEL, sheet_name="의사질문_목록")
    a = pd.read_excel(CORPUS_EXCEL, sheet_name="확장문진_답변키워드")

    is_orig = q["질문출처"].isin(_ORIGINAL_SOURCES)
    qid2stage = dict(zip(q["의사질문ID"], q["단계"]))
    qid2orig = dict(zip(q["의사질문ID"], is_orig))
    a = a.copy()
    a["단계"] = a["의사질문ID"].map(qid2stage)
    a["기존질문여부"] = a["의사질문ID"].map(qid2orig)

    g_q_orig = q[is_orig].groupby("단계").size()
    g_q_aug = q[~is_orig].groupby("단계").size()
    g_a_orig = a[a["기존질문여부"]].groupby("단계").size()
    g_a_aug = a[~a["기존질문여부"]].groupby("단계").size()

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
