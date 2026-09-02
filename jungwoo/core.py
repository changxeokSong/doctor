"""
공통 로직: app.py와 api.py가 함께 사용하는 모델 로딩·검색·글로스 추천 함수.
Streamlit 의존성 없음.
"""
import os
import re
import warnings
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from rank_bm25 import BM25Okapi
from kiwipiepy import Kiwi

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from sentence_transformers import SentenceTransformer
    from sentence_transformers.models import Transformer, Pooling

# ─────────────────────────────────────────────────────────────────────
# 경로
# ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_files     = os.listdir(BASE_DIR)
EXCEL_FILE = os.path.join(BASE_DIR, next(f for f in _files if '0528' in f))
GLOSS_FILE = os.path.join(BASE_DIR, 'test_658_gloss_pool.json')

DEFAULT_Q_MODEL    = "jhgan/ko-sroberta-multitask"
GLOSS_MODEL_NAME   = "jhgan/ko-sroberta-multitask"
HOMONYM_THRESHOLD  = 0.25
BERT_SIM_THRESHOLD = 0.50

# ─────────────────────────────────────────────────────────────────────
# 데이터 로딩
# ─────────────────────────────────────────────────────────────────────
def load_data():
    df = pd.read_excel(EXCEL_FILE, sheet_name=1, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    c = list(df.columns)
    df = df.rename(columns={
        c[0]: 'stage', c[1]: 'category', c[2]: 'question_id',
        c[3]: 'question', c[6]: 'answer_id', c[7]: 'answer',
        c[8]: 'keyword_sl', c[9]: 'keyword_ko',
    })
    for col in ['stage', 'category', 'question', 'answer', 'keyword_sl', 'keyword_ko']:
        df[col] = df[col].fillna('').astype(str).str.strip()
    df = df[df['question'].str.strip() != ''].reset_index(drop=True)

    q_dup_count = (
        df.drop_duplicates('question_id')
          .groupby('question')['question_id'].count()
    )
    df['unique_question'] = df.apply(
        lambda r: (
            f"[{r['stage']}] {r['question']}"
            if q_dup_count.get(r['question'], 1) > 1
            else r['question']
        ),
        axis=1,
    )

    import json
    with open(GLOSS_FILE, encoding='utf-8') as _f:
        _jd = json.load(_f)
    gloss_df = pd.DataFrame([
        {
            'rank':        doc['glossIndex'],
            'gloss':       str(doc['gloss']).strip(),
            'synonyms':    doc.get('synonyms', [str(doc['gloss']).strip()]),
            'description': doc.get('description', ''),
            'text':        doc.get('text', ''),
        }
        for doc in _jd['documents']
    ])
    gloss_df = gloss_df[gloss_df['gloss'] != ''].sort_values('rank').reset_index(drop=True)
    return df, gloss_df


# ─────────────────────────────────────────────────────────────────────
# 모델 로딩
# ─────────────────────────────────────────────────────────────────────
def load_st_model(model_name: str) -> SentenceTransformer:
    try:
        return SentenceTransformer(model_name)
    except Exception:
        word_emb = Transformer(model_name)
        pooling  = Pooling(word_emb.get_word_embedding_dimension(),
                           pooling_mode_mean_tokens=True)
        return SentenceTransformer(modules=[word_emb, pooling])


# ─────────────────────────────────────────────────────────────────────
# 형태소 분석
# ─────────────────────────────────────────────────────────────────────
def extract_kiwi_tokens(text: str, kiwi) -> set:
    """명사·동사·형용사 기본형 추출 (길이 2 이상)."""
    TARGET_POS = {'NNG', 'NNP', 'NNB', 'VV', 'VV-I', 'VA', 'VA-I', 'SL', 'XR'}
    tokens = set()
    for token in kiwi.tokenize(text):
        tag = str(token.tag)
        if tag in TARGET_POS and len(token.lemma) > 1:
            tokens.add(token.lemma)
    return tokens


def extract_nouns_kiwi(text: str, kiwi) -> list[str]:
    """명사만 추출 (글로스 매핑용). 빈도 높은 순서로 정렬."""
    NOUN_POS = {'NNG', 'NNP', 'NNB'}
    seen, result = set(), []
    for token in kiwi.tokenize(text):
        tag = str(token.tag)
        if tag in NOUN_POS and len(token.lemma) >= 2 and token.lemma not in seen:
            seen.add(token.lemma)
            result.append(token.lemma)
    return result


# ─────────────────────────────────────────────────────────────────────
# 임베딩 / BM25
# ─────────────────────────────────────────────────────────────────────
def tokenize_ko(text: str):
    return re.sub(r'[^\w가-힣a-zA-Z0-9]', ' ', text).split()


def build_question_embeddings(model, unique_questions: list) -> np.ndarray:
    return model.encode(unique_questions, batch_size=64,
                        show_progress_bar=False).astype(np.float32)


def build_gloss_embeddings(model, glosses: list,
                           gloss_texts: list | None = None) -> np.ndarray:
    """gloss_texts가 있으면 그것을 임베딩 (JSON text 필드), 없으면 글로스명 prefix 사용."""
    if gloss_texts and len(gloss_texts) == len(glosses):
        texts = gloss_texts
    else:
        texts = [f"의료 수어 표제어: {g}" for g in glosses]
    return model.encode(texts, batch_size=128,
                        show_progress_bar=False).astype(np.float32)


def build_bm25(unique_questions: list) -> BM25Okapi:
    return BM25Okapi([tokenize_ko(q) for q in unique_questions])


# ─────────────────────────────────────────────────────────────────────
# RAG 검색
# ─────────────────────────────────────────────────────────────────────
def retrieve_qa(query: str, model, q_embeddings, bm25, questions_df,
                bert_weight=0.4, bm25_weight=0.6) -> dict:
    tokens    = tokenize_ko(query)
    bm25_raw  = np.array(bm25.get_scores(tokens), dtype=np.float32)
    bm25_max  = bm25_raw.max()
    bm25_norm = bm25_raw / bm25_max if bm25_max > 0 else bm25_raw

    q_emb     = model.encode([query], show_progress_bar=False).astype(np.float32)
    bert_sims = cosine_similarity(q_emb, q_embeddings)[0]
    bert_min, bert_max = bert_sims.min(), bert_sims.max()
    bert_norm = (bert_sims - bert_min) / (bert_max - bert_min + 1e-9)

    hybrid = bm25_weight * bm25_norm + bert_weight * bert_norm
    top_i  = int(np.argmax(hybrid))
    row    = questions_df.iloc[top_i]

    q_tokens = set(tokenize_ko(query))
    m_tokens = set(tokenize_ko(row['question']))
    evidence = sorted(q_tokens & m_tokens, key=len, reverse=True)

    return {
        'question_id': row['question_id'],
        'question':    row['question'],
        'stage':       row['stage'],
        'category':    row['category'],
        'similarity':  float(hybrid[top_i]),
        'bm25_score':  float(bm25_norm[top_i]),
        'bert_score':  float(bert_sims[top_i]),
        'evidence':    evidence,
    }


# ─────────────────────────────────────────────────────────────────────
# 글로스 추천 — 단어별 top-1 (API용)
# ─────────────────────────────────────────────────────────────────────
def recommend_top1_per_word(
    answers_df: pd.DataFrame,
    gloss_model,
    gloss_df: pd.DataFrame,
    g_embeddings: np.ndarray,
    kiwi,
    question_text: str = "",
) -> list[dict]:
    """
    각 답변에서 명사를 추출하고, 단어(명사)별로 top-1 글로스를 반환.
    반환 형태:
    [
      {
        "answer_id": "Q0001-A01",
        "answer": "허리가 아파요",
        "keywords": [
          {"word": "허리", "gloss": "허리", "score": 1.0, "match_type": "exact"},
          ...
        ]
      },
      ...
    ]
    """
    gloss_list = gloss_df['gloss'].tolist()
    # synonym → (gloss, origin/rank) 역방향 매핑 (exact 매칭용)
    syn_to_gloss: dict[str, tuple[str, int]] = {}
    for idx, row_g in gloss_df.iterrows():
        origin = int(row_g['rank'])
        for syn in row_g.get('synonyms', [row_g['gloss']]):
            if syn and syn not in syn_to_gloss:
                syn_to_gloss[str(syn).strip()] = (row_g['gloss'], origin)

    results = []
    for _, row in answers_df.iterrows():
        ans_text   = str(row['answer']).strip()
        kw_sl_text = str(row.get('keyword_sl', '')).strip()

        # 명사 추출 (답변 + 질문 + 수어키워드 합산)
        combined = f"{question_text} {ans_text} {kw_sl_text}"
        nouns = extract_nouns_kiwi(combined, kiwi)

        keywords = []
        for word in nouns:
            if len(word) < 2:
                continue
            # Tier 1: synonym 사전에 정확히 있는 경우
            if word in syn_to_gloss:
                matched_gloss, origin = syn_to_gloss[word]
                keywords.append({
                    "word":       word,
                    "gloss":      matched_gloss,
                    "origin":     origin,
                    "score":      1.0,
                    "match_type": "exact",
                })
            else:
                # Tier 2: BERT 유사도 top-1
                word_emb = gloss_model.encode(
                    [f"의료 수어 표제어: {word}"],
                    show_progress_bar=False,
                ).astype(np.float32)
                sims    = cosine_similarity(word_emb, g_embeddings)[0]
                top_idx = int(np.argmax(sims))
                score   = float(sims[top_idx])
                if score >= HOMONYM_THRESHOLD:
                    keywords.append({
                        "word":       word,
                        "gloss":      gloss_list[top_idx],
                        "origin":     int(gloss_df.iloc[top_idx]['rank']),
                        "score":      round(score, 4),
                        "match_type": "bert",
                    })

        results.append({
            "answer_id": row['answer_id'],
            "answer":    ans_text,
            "keywords":  keywords,
        })

    return results
