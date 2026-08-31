"""수어 표제어(Gloss) 사전 로드 + 검색.
표제어 임베딩은 행(Gloss_Name 전체, 동의어 콤마로 결합된 문자열) 단위가 아니라 '동의어 단위'로 임베딩한다 -
전체를 통째로 임베딩하면 "질환"처럼 정확한 단어가 들어있어도 나머지 동의어들 때문에 흐려져 유사도가
오히려 낮게 나오는 문제가 실측으로 확인됐다 (예: "질환" 쿼리 -> 정확일치 행이 3760개 중 10위, 0.70,
"몸살" 등 무관한 단어보다 낮음). 동의어 단위로 쪼개 임베딩하고, 검색 시 같은 표제어(행)끼리는
최댓값을 취해 순위를 매기면 정확일치가 항상 1위(유사도 1.0)로 나온다."""
import os
from functools import lru_cache

import numpy as np
import pandas as pd

from app.config import GLOSS_EXCEL, EMB_MODEL_NAME, GLOSS_TOP_K
from app.embedding import load_embedder, cache_suffix, prep_query, prep_passage


def _is_jamo_only(s):
    return all(0x3131 <= ord(c) <= 0x318E for c in str(s))


@lru_cache(maxsize=None)
def load_gloss_dict():
    df = pd.read_excel(GLOSS_EXCEL, sheet_name="Sign_Gloss")
    jamo_mask = df["Gloss_Name"].apply(_is_jamo_only).values
    df = df[~jamo_mask].reset_index(drop=True)
    return df


def _split_synonyms(name: str):
    """Gloss_Name("편찮다,아프다" 처럼 동의어가 콤마로 묶인 문자열)을 개별 동의어로 쪼갠다.
    "(맛이)짜다" 같은 괄호 설명이 붙은 항목은 순수 형태("짜다")도 함께 반환한다."""
    keys = []
    for syn in str(name).split(","):
        syn = syn.strip()
        syn_bare = syn.split(")")[-1].strip() if ")" in syn else syn
        for key in {syn, syn_bare}:
            if key:
                keys.append(key)
    return keys


@lru_cache(maxsize=None)
def gloss_category_by_origin() -> dict[int, str]:
    """origin_number -> Gloss_Category. 세부분류별 카테고리 가산점(services.py의
    SUBCATEGORY_CATEGORY_PRIORITY) 계산에 쓴다."""
    gloss_df = load_gloss_dict()
    return {int(row["Origin_Number"]): row["Gloss_Category"] for _, row in gloss_df.iterrows()}


@lru_cache(maxsize=None)
def build_exact_gloss_index():
    """동의어 단위 정확일치 조회용 인덱스. 행 위치(row_idx)도 같이 저장한다."""
    gloss_df = load_gloss_dict()
    index = {}
    for i, row in gloss_df.iterrows():
        name = str(row["Gloss_Name"])
        for key in _split_synonyms(name):
            if key not in index:
                index[key] = (name, int(row["Origin_Number"]), i)
    return index


@lru_cache(maxsize=None)
def build_gloss_synonym_embeddings(model_name: str = EMB_MODEL_NAME):
    gloss_df = load_gloss_dict()
    embedder = load_embedder(model_name)
    synonyms, row_idx_of_syn = [], []
    for i, row in gloss_df.iterrows():
        seen_here = set()
        for key in _split_synonyms(row["Gloss_Name"]):
            if key not in seen_here:
                synonyms.append(key)
                row_idx_of_syn.append(i)
                seen_here.add(key)
    cache_path = f"./cache/gloss_synonym_embeddings__{cache_suffix(model_name)}.npy"
    if os.path.exists(cache_path):
        syn_emb = np.load(cache_path)
    else:
        syn_emb = embedder.encode(prep_passage(model_name, synonyms), normalize_embeddings=True, batch_size=64)
        np.save(cache_path, syn_emb)
    return np.array(row_idx_of_syn), syn_emb


def _rank_for_query(syn_sims, gloss_syn_row_idx, gloss_df, exact_gloss_index, keyword, top_k):
    """쿼리 하나의 동의어별 유사도(syn_sims)로부터 (exact_hit, hits)를 계산한다.
    gloss_lookup/gloss_lookup_batch가 공유하는 집계 로직."""
    row_max: dict[int, float] = {}
    for sim, row_idx in zip(syn_sims, gloss_syn_row_idx):
        row_idx = int(row_idx)
        if sim > row_max.get(row_idx, -1.0):
            row_max[row_idx] = float(sim)

    ranked = sorted(row_max.items(), key=lambda x: -x[1])[:top_k]
    hits = [
        (gloss_df.iloc[r]["Gloss_Name"], int(gloss_df.iloc[r]["Origin_Number"]), round(score, 4))
        for r, score in ranked
    ]

    exact = exact_gloss_index.get(keyword.strip())
    exact_hit = None
    if exact:
        name, origin_number, row_idx = exact
        exact_hit = (name, origin_number, round(row_max.get(row_idx, float(syn_sims.max())), 4))
    return exact_hit, hits


def gloss_lookup(keyword: str, top_k: int = GLOSS_TOP_K, model_name: str = EMB_MODEL_NAME):
    """키워드 1개를 한 번만 임베딩해서 (정확일치 여부, 유사도 top-k 후보)를 함께 계산한다.
    반환: (exact_hit 또는 None, [(표제어, origin_number, score), ...])"""
    return gloss_lookup_batch([keyword], top_k=top_k, model_name=model_name)[0]


def gloss_lookup_batch(keywords: list, top_k: int = GLOSS_TOP_K, model_name: str = EMB_MODEL_NAME):
    """gloss_lookup의 배치판 — 키워드 여러 개를 embedder.encode() 한 번으로 같이 인코딩한다.
    (한 파이프라인 요청에 답변 후보가 여러 개고 후보마다 키워드가 여럿이면, 키워드 개수만큼
    encode()를 따로따로 호출하는 게 실측으로 확인된 지연시간의 대부분을 차지했다 — SentenceTransformer는
    호출 1회당 고정 오버헤드가 있어서 작은 입력을 여러 번 나눠 부르는 것보다 한 번에 배치로 부르는 게
    훨씬 빠르다.) 반환: [(exact_hit, hits), ...] — keywords와 같은 순서."""
    if not keywords:
        return []
    gloss_df = load_gloss_dict()
    exact_gloss_index = build_exact_gloss_index()
    gloss_syn_row_idx, gloss_syn_embeddings = build_gloss_synonym_embeddings(model_name)
    embedder = load_embedder(model_name)

    q_batch = embedder.encode(prep_query(model_name, keywords), normalize_embeddings=True)  # (N, D)
    sims_batch = gloss_syn_embeddings @ q_batch.T  # (num_synonyms, N)

    return [
        _rank_for_query(sims_batch[:, i], gloss_syn_row_idx, gloss_df, exact_gloss_index, kw, top_k)
        for i, kw in enumerate(keywords)
    ]
