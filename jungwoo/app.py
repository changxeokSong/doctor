import os
import re
import warnings
from html import escape as _html_escape
def hx(value):
    return _html_escape(str(value if value is not None else ''))
import pandas as pd
import numpy as np
import streamlit as st
from sklearn.metrics.pairwise import cosine_similarity
from rank_bm25 import BM25Okapi

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from sentence_transformers import SentenceTransformer
    from sentence_transformers.models import Transformer, Pooling

from kiwipiepy import Kiwi
from core import recommend_top1_per_word

# ────────────────────────────────────────────────────────────
# 파일 경로
# ────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_files     = os.listdir(BASE_DIR)
EXCEL_FILE = os.path.join(BASE_DIR, next(f for f in _files if '0528' in f))
GLOSS_FILE = os.path.join(BASE_DIR, 'test_658_gloss_pool.json')

# ────────────────────────────────────────────────────────────
# 선택 가능한 Q 검색 모델 목록
# ────────────────────────────────────────────────────────────
AVAILABLE_MODELS = {
    "jhgan/ko-sroberta-multitask":                                   "Ko-SRoBERTa (기본, 한국어 STS)",
    "snumin44/sap-bert-ko-en":                                       "SAP-BERT Ko-En (의료 특화)",
    "madatnlp/km-bert":                                              "KM-BERT (한국어 의료 특화, MedSTS)",
    "snumin44/medical-biencoder-ko-bert-question":                   "Medical Bi-Encoder Q (의료 QA 특화)",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2":  "Multilingual MiniLM (다국어)",
}

# 글로스 임베딩: 문장 유사도 특화 모델 (SAP-BERT는 엔티티 정규화 목적이라
# 의료 용어끼리 모두 유사하게 나오는 문제 → ko-sroberta로 교체)
GLOSS_MODEL_NAME = "jhgan/ko-sroberta-multitask"

# 동음이의어 검증 임계값 (1·2순위 exact/keyword 매칭에 적용)
HOMONYM_THRESHOLD = 0.25

# 3순위 BERT 추천 최소 임계값
# ko-sroberta 기준 0.5 이상만 표시 → 무관한 글로스 차단
BERT_SIM_THRESHOLD = 0.50


# ────────────────────────────────────────────────────────────
# 데이터 로딩
# ────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="데이터 로딩 중...")
def load_data():
    df = pd.read_excel(EXCEL_FILE, sheet_name=1, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    c = list(df.columns)

    df = df.rename(columns={
        c[0]: 'stage',
        c[1]: 'category',
        c[2]: 'question_id',
        c[3]: 'question',
        c[6]: 'answer_id',
        c[7]: 'answer',
        c[8]: 'keyword_sl',
        c[9]: 'keyword_ko',
    })

    for col in ['stage', 'category', 'question', 'answer', 'keyword_sl', 'keyword_ko']:
        df[col] = df[col].fillna('').astype(str).str.strip()

    df = df[df['question'].str.strip() != ''].reset_index(drop=True)

    # ── 데이터 정제: 중복 질문 텍스트 처리 ──
    # 동일 질문 텍스트가 다른 stage/question_id에 존재하는 경우
    # (예: Q0038 / Q0068 모두 "통증이 일정하게 아파요?")
    # → 임베딩/BM25용 unique_question 컬럼에 "[stage] question" 형태로 구분
    q_dup_count = (
        df.drop_duplicates('question_id')
          .groupby('question')['question_id']
          .count()
    )  # Series: {question_text → count}
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


# ────────────────────────────────────────────────────────────
# 모델 로딩 유틸
# ────────────────────────────────────────────────────────────
def _is_sentence_transformer(model_name: str) -> bool:
    """sentence-transformers hub에 직접 올라온 모델 여부 추정."""
    ST_PREFIXES = ("sentence-transformers/", "jhgan/", "snunlp/", "BM-K/")
    return any(model_name.startswith(p) for p in ST_PREFIXES)


@st.cache_resource(show_spinner="형태소 분석기 로딩 중...", ttl=None)
def load_kiwi():
    return Kiwi()


def extract_kiwi_tokens(text: str, kiwi) -> set:
    """
    Kiwi 형태소 분석으로 의미 단위 토큰 추출 (kiwi.tokenize 사용).
    - NNG/NNP/NNB: 명사 lemma 그대로
    - VV/VV-I/VA/VA-I: 동사·형용사 기본형 (아픈→아프다, 걸을→걷다, 누워→눕다)
    - SL: 영문/외래어
    길이 1 이하 토큰은 오매칭 방지를 위해 제외.
    """
    TARGET_POS = {'NNG', 'NNP', 'NNB', 'VV', 'VV-I', 'VA', 'VA-I', 'SL', 'XR'}
    tokens = set()
    for token in kiwi.tokenize(text):
        tag = str(token.tag)
        if tag in TARGET_POS and len(token.lemma) > 1:
            tokens.add(token.lemma)
    return tokens


@st.cache_resource(show_spinner="Q 검색 모델 로딩 중...", ttl=None)
def load_model(model_name: str) -> SentenceTransformer:
    """SentenceTransformer 또는 HuggingFace BERT를 ST 래퍼로 로드."""
    try:
        return SentenceTransformer(model_name)
    except Exception:
        word_emb = Transformer(model_name)
        pooling  = Pooling(word_emb.get_word_embedding_dimension(),
                           pooling_mode_mean_tokens=True)
        return SentenceTransformer(modules=[word_emb, pooling])


@st.cache_resource(show_spinner="글로스 임베딩 모델 로딩 중...", ttl=None)
def load_gloss_model(model_name: str) -> SentenceTransformer:
    """글로스 전용 SAP-BERT 모델 로드."""
    try:
        return SentenceTransformer(model_name)
    except Exception:
        word_emb = Transformer(model_name)
        pooling  = Pooling(word_emb.get_word_embedding_dimension(),
                           pooling_mode_mean_tokens=True)
        return SentenceTransformer(modules=[word_emb, pooling])


# ────────────────────────────────────────────────────────────
# 임베딩 / BM25
# ────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="질문 임베딩 생성 중...", ttl=None)
def build_question_embeddings(_model, unique_questions: tuple, model_name: str):
    """model_name을 캐시 키에 포함 → 모델 교체 시 자동 무효화."""
    return _model.encode(list(unique_questions), batch_size=64,
                         show_progress_bar=False).astype(np.float32)


@st.cache_resource(show_spinner="글로스 임베딩 생성 중...", ttl=None)
def build_gloss_embeddings(_model, glosses: tuple, model_name: str,
                           gloss_texts: tuple = ()):
    """JSON text 필드(설명 포함)로 글로스 임베딩. 없으면 글로스명 prefix 사용."""
    if gloss_texts and len(gloss_texts) == len(glosses):
        texts = list(gloss_texts)
    else:
        texts = [f"의료 수어 표제어: {g}" for g in glosses]
    return _model.encode(texts, batch_size=128,
                         show_progress_bar=False).astype(np.float32)


def tokenize_ko(text: str):
    return re.sub(r'[^\w가-힣a-zA-Z0-9]', ' ', text).split()


@st.cache_resource(show_spinner="BM25 인덱스 생성 중...", ttl=None)
def build_bm25(unique_questions: tuple):
    tokenized = [tokenize_ko(q) for q in unique_questions]
    return BM25Okapi(tokenized)


# ────────────────────────────────────────────────────────────
# RAG: BM25 + BERT 하이브리드 검색
# ────────────────────────────────────────────────────────────
def get_bm25_evidence(query: str, matched_question: str):
    q_tokens = set(tokenize_ko(query))
    m_tokens = set(tokenize_ko(matched_question))
    common   = q_tokens & m_tokens
    return sorted(common, key=len, reverse=True)


def sel_category_matches(sel_cat, ai_cat, df, ai_qid):
    row = df[df['question_id'] == ai_qid]
    if row.empty:
        return False
    return row.iloc[0]['category'] == sel_cat


def retrieve_qa(query: str, model, q_embeddings, bm25, questions_df,
                bert_weight: float = 0.4, bm25_weight: float = 0.6):
    """
    BM25(60%) + BERT(40%) 하이브리드.
    unique_question 컬럼 기준으로 검색 → 중복 질문 텍스트 구분.
    """
    tokens   = tokenize_ko(query)
    bm25_raw = np.array(bm25.get_scores(tokens), dtype=np.float32)
    bm25_max = bm25_raw.max()
    bm25_norm = bm25_raw / bm25_max if bm25_max > 0 else bm25_raw

    q_emb     = model.encode([query], show_progress_bar=False).astype(np.float32)
    bert_sims  = cosine_similarity(q_emb, q_embeddings)[0]
    bert_min, bert_max = bert_sims.min(), bert_sims.max()
    bert_norm  = (bert_sims - bert_min) / (bert_max - bert_min + 1e-9)

    hybrid = bm25_weight * bm25_norm + bert_weight * bert_norm
    top_i  = int(np.argmax(hybrid))
    row    = questions_df.iloc[top_i]

    evidence = get_bm25_evidence(query, row['question'])

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


# ────────────────────────────────────────────────────────────
# 글로스 추천 (per-answer, 3-tier hybrid)
# ────────────────────────────────────────────────────────────
def build_context_text(question: str, answer: str, keyword_sl: str, keyword_ko: str) -> str:
    parts = []
    if question.strip():
        parts.append(f"질문: {question.strip()}")
    if answer.strip():
        parts.append(f"답변: {answer.strip()}")
    if keyword_sl.strip() and keyword_sl != 'nan':
        parts.append(f"수어키워드: {keyword_sl.strip()}")
    if keyword_ko.strip() and keyword_ko != 'nan':
        parts.append(f"자연어: {keyword_ko.strip()}")
    return ' '.join(parts)


def recommend_glosses_per_answer(answers_df, q_model, gloss_model,
                                  gloss_df, g_embeddings, kiwi=None,
                                  question_text: str = '',
                                  query_emb=None, min_cnt=2, max_cnt=5):
    """
    답변 행마다 개별 표제어 추천 + 쿼리 대비 유사도 반환.
    - 문맥 임베딩(Q 모델): Q+A+키워드 전체 → 각 답변별 유사도 계산
    - 글로스 임베딩(SAP-BERT): 의료 특화 표제어 임베딩
    - 동음이의어 처리: 문맥 유사도 < HOMONYM_THRESHOLD 면 exact 매칭도 제외
    """
    gloss_list = gloss_df['gloss'].tolist()

    # 문맥 텍스트 + 임베딩 (Q 모델)
    context_texts = []
    for _, row in answers_df.iterrows():
        ctx = build_context_text(
            question_text,
            str(row['answer']),
            str(row['keyword_sl']),
            str(row['keyword_ko']),
        )
        context_texts.append(ctx)

    ctx_embs = q_model.encode(context_texts, show_progress_bar=False).astype(np.float32)

    # 쿼리 ↔ 각 답변 유사도
    if query_emb is not None:
        q_sims = cosine_similarity(query_emb, ctx_embs)[0]
    else:
        q_sims = np.zeros(len(answers_df))

    # 문맥 임베딩(Q 모델) ↔ 글로스 임베딩(SAP-BERT) 유사도
    # 두 모델의 차원이 다를 수 있으므로 문맥 임베딩도 SAP-BERT로 재인코딩
    ctx_embs_sap = gloss_model.encode(context_texts, show_progress_bar=False).astype(np.float32)
    gloss_sims   = cosine_similarity(ctx_embs_sap, g_embeddings)  # (n_ans, n_glosses)

    results = []
    for i, (_, row) in enumerate(answers_df.iterrows()):
        ans_text   = str(row['answer']).strip()
        kw_sl_text = str(row['keyword_sl']).strip()
        kw_ko_text = str(row['keyword_ko']).strip()
        full_text  = ' '.join([ans_text, kw_sl_text, kw_ko_text])

        # 공백 분리 토큰 (fallback)
        space_tokens     = set(re.sub(r'[^\w가-힣a-zA-Z0-9]', ' ', full_text).split())
        kw_sl_space_toks = set(re.sub(r'[^\w가-힣a-zA-Z0-9]', ' ', kw_sl_text).split())

        # Kiwi 형태소 토큰: 명사 원형 + 동사·형용사 기본형
        if kiwi is not None:
            morph_tokens     = extract_kiwi_tokens(full_text, kiwi)
            kw_sl_morph_toks = extract_kiwi_tokens(kw_sl_text, kiwi)
        else:
            morph_tokens     = set()
            kw_sl_morph_toks = set()

        # 합집합: 형태소 + 공백 분리 (startswith 보완)
        word_tokens  = morph_tokens  | space_tokens
        kw_sl_tokens = kw_sl_morph_toks | kw_sl_space_toks
        row_sims     = gloss_sims[i]

        # 글로스별 synonym 목록 (JSON 기반)
        _has_synonyms = 'synonyms' in gloss_df.columns

        def token_match(g: str, tokens: set, full: str, g_idx: int = -1) -> bool:
            """
            형태소 기반 + 조사 처리 + synonym 통합 매칭.
            1) 글로스 자체 또는 각 synonym을 형태소 집합에서 정확 매칭
            2) 공백 토큰 startswith (조사 처리)
            3) 복합어/multi-word: 원문 substring
            최소 2자 이상.
            """
            # 매칭 대상: 글로스 + synonym 목록
            candidates = [g]
            if _has_synonyms and g_idx >= 0:
                syns = gloss_df.iloc[g_idx].get('synonyms', [])
                candidates += [str(s) for s in syns if s and s != g]

            for cand in candidates:
                if len(cand) < 2:
                    continue
                cand_words = re.sub(r'[^\w가-힣a-zA-Z0-9]', ' ', cand).split()
                if len(cand_words) == 1:
                    if cand in tokens:
                        return True
                    if any(tok.startswith(cand) for tok in space_tokens):
                        return True
                else:
                    if cand in full:
                        return True
            return False

        # ── 1순위: 단어 직접 일치 + 동음이의어 검증 ──
        exact = []
        for j, g in enumerate(gloss_list):
            if not g:
                continue
            if not token_match(g, word_tokens, full_text, g_idx=j):
                continue
            ctx_gloss_sim = float(row_sims[j])
            if ctx_gloss_sim < HOMONYM_THRESHOLD:
                continue
            exact.append({
                'gloss':      g,
                'match_type': 'exact',
                'similarity': ctx_gloss_sim,
                'best_word':  g,
                'rank':       int(gloss_df.iloc[j]['rank']),
            })
        exact.sort(key=lambda x: x['rank'])

        # ── 2순위: keyword_sl 컬럼 매칭 + 동음이의어 검증 ──
        used = {e['gloss'] for e in exact}
        kw_matched = []
        for j, g in enumerate(gloss_list):
            if not g or g in used:
                continue
            if not token_match(g, kw_sl_tokens, kw_sl_text, g_idx=j):
                continue
            ctx_gloss_sim = float(row_sims[j])
            if ctx_gloss_sim < HOMONYM_THRESHOLD:
                continue
            kw_matched.append({
                'gloss':      g,
                'match_type': 'keyword',
                'similarity': ctx_gloss_sim,
                'best_word':  g,
                'rank':       int(gloss_df.iloc[j]['rank']),
            })
        kw_matched.sort(key=lambda x: x['rank'])

        # ── 3순위: SAP-BERT 문맥 유사도 ──
        used |= {k['gloss'] for k in kw_matched}
        bert_ranked = []
        # BERT_SIM_THRESHOLD 이상인 글로스만 포함 (무관한 의료용어 차단)
        for idx in np.argsort(row_sims)[::-1]:
            sim_val = float(row_sims[idx])
            if sim_val < BERT_SIM_THRESHOLD:
                break   # 내림차순이므로 이후는 모두 낮음
            g = gloss_list[idx]
            if g not in used:
                bert_ranked.append({
                    'gloss':      g,
                    'match_type': 'bert',
                    'similarity': sim_val,
                    'best_word':  '문맥 유사도',
                    'rank':       int(gloss_df.iloc[idx]['rank']),
                })
            if len(bert_ranked) >= max_cnt:
                break

        combined = exact[:max_cnt]
        rem = max_cnt - len(combined)
        if rem > 0:
            combined += kw_matched[:rem]
        rem = max_cnt - len(combined)
        if rem > 0:
            combined += bert_ranked[:rem]
        # min_cnt 보장: 임계값 이하라도 최소 개수는 채움
        if len(combined) < min_cnt:
            fallback = [
                {'gloss': gloss_list[idx], 'match_type': 'bert',
                 'similarity': float(row_sims[idx]), 'best_word': '문맥 유사도',
                 'rank': int(gloss_df.iloc[idx]['rank'])}
                for idx in np.argsort(row_sims)[::-1]
                if gloss_list[idx] not in {c['gloss'] for c in combined}
            ]
            combined += fallback[:min_cnt - len(combined)]

        results.append({
            'answer_id':  row['answer_id'],
            'answer':     ans_text,
            'keyword_sl': kw_sl_text,
            'keyword_ko': kw_ko_text,
            'query_sim':  float(q_sims[i]),
            'glosses':    combined[:max_cnt],
        })

    results.sort(key=lambda x: x['query_sim'], reverse=True)
    return results


# ════════════════════════════════════════════════════════════
# Streamlit UI
# ════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="통증의학과 Q&A 검색",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# html/styles.css · index.html · analysis.html · catalog.html 과 같은 계층
st.markdown("""
<style>
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main,
[data-testid="stHeader"] { background: #f0f0f5 !important; }
[data-testid="block-container"] {
    padding: 40px 18px 64px !important;
    max-width: 1180px !important;
}
section[data-testid="stSidebar"],
[data-testid="collapsedControl"] { display: none !important; }
header [data-testid="stToolbar"] { visibility: hidden; }

.stApp, .stMarkdown, p, label, span, div {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4 { color: #1d1d1f !important; }
[data-testid="stCaptionContainer"] p { font-size: 12px !important; color: #8e8e93 !important; }

.stButton > button,
[data-testid="stBaseButton-primary"],
[data-testid="baseButton-primary"],
button[kind="primary"] {
    background: #636af5 !important; color: #fff !important;
    border: none !important; border-radius: 9px !important;
    font-size: 14px !important; font-weight: 700 !important;
    padding: 11px 24px !important;
}
.stButton > button:hover,
[data-testid="stBaseButton-primary"]:hover,
button[kind="primary"]:hover { background: #4f56e0 !important; }
[data-testid="stBaseButton-secondary"],
[data-testid="baseButton-secondary"],
button[kind="secondary"] {
    background: #fff !important; color: #3c3c43 !important;
    border: 1px solid #d1d1d6 !important; border-radius: 9px !important;
    font-size: 13px !important; font-weight: 600 !important;
}

[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] > div > div {
    background: #fff !important;
    border: 1.5px solid #d1d1d6 !important;
    border-radius: 10px !important;
    font-size: 14px !important;
}
[data-testid="stTextArea"] textarea { min-height: 76px !important; }
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #636af5 !important;
    box-shadow: none !important;
}
[data-testid="stSelectbox"] label,
[data-testid="stSlider"] label,
[data-testid="stTextInput"] label,
[data-testid="stTextArea"] label {
    font-size: 11px !important; color: #636366 !important; font-weight: 700 !important;
}

[data-testid="stAlert"] { border-radius: 10px !important; font-size: 13px !important; }
hr { display: none !important; }
[data-testid="stForm"] {
    background: #fff !important;
    border: 1px solid #e5e5ea !important;
    border-radius: 12px !important;
    padding: 18px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,.04) !important;
}
[data-testid="stForm"] [data-testid="stVerticalBlockBorderWrapper"] {
    border: none !important; box-shadow: none !important;
}

.app-header { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.app-header h1 { font-size: 22px; font-weight: 700; line-height: 1.25; color: #1d1d1f; margin: 0; }
.app-header p { font-size: 13px; color: #636366; margin-top: 4px; }
.app-nav { display: flex; align-items: center; gap: 14px; }
.app-link { font-size: 13px; font-weight: 600; color: #636af5; text-decoration: none; white-space: nowrap; }

.card { background: #fff; border: 1px solid #e5e5ea; border-radius: 12px; padding: 18px; box-shadow: 0 8px 24px rgba(0,0,0,.04); margin-bottom: 18px; }
.card-title { font-size: 13px; font-weight: 800; margin-bottom: 12px; color: #1d1d1f; }
.card-note { font-size: 12px; color: #8e8e93; margin-top: 8px; }

.result-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.result-label { font-size: 13px; font-weight: 800; color: #1d1d1f; }
.result-meta { font-size: 12px; color: #8e8e93; }
.result-section-title { font-size: 12px; font-weight: 800; color: #636366; margin: 16px 0 10px; }

.stat-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; }
.stat-card { background: #f7f7fa; border: 1px solid #ececf2; border-radius: 10px; padding: 11px 12px; }
.stat-card span { display: block; font-size: 11px; color: #636366; font-weight: 700; margin-bottom: 4px; }
.stat-card strong { font-size: 20px; line-height: 1.1; font-variant-numeric: tabular-nums; color: #1d1d1f; }
.stat-card small { font-size: 11px; color: #8e8e93; margin-left: 3px; }

.kv { background: #f5f5f7; border-radius: 10px; padding: 13px 15px; font-size: 13px; color: #3c3c43; line-height: 1.6; }
.kv div + div { margin-top: 3px; }

.pool-list { display: flex; flex-direction: column; gap: 6px; }
.pool-item { background: #fff; border: 1px solid #e5e5ea; border-radius: 8px; padding: 9px 11px; font-size: 13px; color: #1d1d1f; }
.pool-core { font-size: 12px; font-weight: 600; color: #0a7d32; margin-top: 3px; }
.pool-core.missing { color: #b00020; font-weight: 500; }
.pool-meta { font-size: 12px; color: #8e8e93; margin-top: 2px; }

.keyword-list { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 8px; }
.kw { display: inline-flex; align-items: baseline; gap: 6px; border-radius: 22px; padding: 8px 16px; border: 1px solid transparent; line-height: 1.35; }
.kw b { font-size: 16px; font-weight: 700; }
.kw .idx { font-size: 11px; opacity: .6; font-variant-numeric: tabular-nums; }
.kw.t1 { background: #1a7f37; color: #fff; }
.kw.t1 .idx { color: #fff; opacity: .75; }

[data-testid="stRadio"] [role="radiogroup"] {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    gap: 18px !important;
}
[data-testid="stRadio"] [role="radiogroup"] label {
    display: inline-flex !important;
    flex-direction: row !important;
    align-items: center !important;
    white-space: nowrap !important;
    gap: 6px !important;
}
[data-testid="stRadio"] [role="radiogroup"] label p {
    font-size: 13px !important;
    font-weight: 600 !important;
    color: #3c3c43 !important;
    white-space: nowrap !important;
    margin: 0 !important;
}

.empty-note { font-size: 13px; color: #8e8e93; }
.notice { border-radius: 10px; padding: 13px 15px; font-size: 13px; line-height: 1.6; }
.notice.warn { background: #fff8e1; border: 1px solid #ffe082; color: #7a5b0b; }
.hint { font-size: 12px; color: #8e8e93; }

.table { width: 100%; border-collapse: collapse; font-size: 12px; }
.table th { background: #f5f5f7; padding: 8px 9px; text-align: left; color: #636366; font-weight: 700; border-bottom: 1px solid #e5e5ea; }
.table td { border-bottom: 1px solid #f0f0f5; padding: 7px 9px; vertical-align: top; color: #1d1d1f; }
.table .gl { color: #1a7f37; font-weight: 700; }
.table-scroll { max-height: 520px; overflow-y: auto; border: 1px solid #f0f0f5; border-radius: 8px; }
.row-number { color: #8e8e93; font-variant-numeric: tabular-nums; }

.json-panel { border: 1px solid #e5e5ea; border-radius: 9px; overflow: hidden; background: #fafafc; }
.json-panel summary { cursor: pointer; padding: 9px 11px; font-size: 12px; font-weight: 700; color: #3c3c43; }
.json-panel pre {
    max-height: 480px; overflow: auto; border-top: 1px solid #ececf2; padding: 12px;
    background: #1e1f24; color: #e8e8ed;
    font: 11px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    white-space: pre !important;
    overflow-wrap: normal;
    word-break: keep-all;
    margin: 0;
}

@media (max-width: 720px) {
    .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .app-header { flex-direction: column; align-items: flex-start; gap: 8px; }
}
@media (min-width: 721px) and (max-width: 980px) {
    .stat-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
</style>
""", unsafe_allow_html=True)

# ── 페이지 전환 (HTML app-nav 역할) ──
if 'page' not in st.session_state:
    st.session_state.page = 'qa'

st.markdown("""
<div class="app-header">
  <div>
    <h1>통증의학과 초진 Q&amp;A 검색</h1>
    <p>의사 질문을 입력하면 문진 단계·세부 분류를 파악하고 답변과 표제어를 추천합니다.</p>
  </div>
</div>
""", unsafe_allow_html=True)

_page_label = st.segmented_control(
    "화면",
    options=["추천 화면", "API 테스트"],
    default="추천 화면" if st.session_state.page == 'qa' else "API 테스트",
    key="page_seg",
    label_visibility="collapsed",
)
if _page_label:
    st.session_state.page = 'qa' if _page_label == '추천 화면' else 'api'

# ── 모델 선택 (사이드바 대신 본문 카드) ──
sel_model_name = st.selectbox(
    "검색 모델",
    options=list(AVAILABLE_MODELS.keys()),
    format_func=lambda k: AVAILABLE_MODELS[k],
    key="model_selector",
)
if st.session_state.get("_active_model") != sel_model_name:
    st.session_state["_active_model"] = sel_model_name
    for key in ['step', 'match', 'answers', 'glosses',
                'query', 'final_qid', 'sel_stage', 'sel_cat',
                'per_answer', 'input_mode']:
        st.session_state.pop(key, None)

# 데이터 & 모델 로드
df, gloss_df   = load_data()
MODEL_NAME     = sel_model_name
q_model        = load_model(MODEL_NAME)
gloss_model    = load_gloss_model(GLOSS_MODEL_NAME)
kiwi           = load_kiwi()

questions_df = df.drop_duplicates('question_id')[
    ['question_id', 'question', 'unique_question', 'stage', 'category']
].reset_index(drop=True)

# 임베딩은 unique_question 기준 (중복 질문 텍스트 구분)
q_embeddings = build_question_embeddings(
    q_model,
    tuple(questions_df['unique_question'].tolist()),
    MODEL_NAME,
)
g_embeddings = build_gloss_embeddings(
    gloss_model,
    tuple(gloss_df['gloss'].tolist()),
    GLOSS_MODEL_NAME,
    gloss_texts=tuple(gloss_df['text'].tolist()) if 'text' in gloss_df.columns else (),
)
bm25 = build_bm25(tuple(questions_df['unique_question'].tolist()))

for key, default in {
    'step': 1, 'match': None, 'answers': None, 'glosses': None, 'query': '',
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

dup_n = int((questions_df['unique_question'] != questions_df['question']).sum())


def _reset_query():
    for key in ['step', 'match', 'answers', 'glosses', 'query',
                'final_qid', 'sel_stage', 'sel_cat', 'per_answer']:
        st.session_state.pop(key, None)


def _gloss_pills(items, id_key='rank'):
    if not items:
        return '<div class="pool-core missing">직접 일치하는 글로스 없음</div>'
    pills = ''.join(
        f'<span class="kw t1"><b>{hx(g["gloss"])}</b>'
        f'<span class="idx">#{hx(g.get(id_key, g.get("origin", "")))}</span></span>'
        for g in items
    )
    return f'<div class="keyword-list">{pills}</div>'


# ════════════════════════════════════════════════════════════
# 추천 화면  (index.html + analysis.html 구조)
# ════════════════════════════════════════════════════════════
if st.session_state.page == 'qa':
    st.markdown('<div class="card-title">질문 입력</div>', unsafe_allow_html=True)
    input_mode = st.radio(
        "입력 방식",
        ["직접 입력", "목록에서 선택"],
        horizontal=True,
        label_visibility="collapsed",
        key="input_mode_radio",
    )

    user_query = ""
    search_clicked = False

    if input_mode == "직접 입력":
        with st.form("step1_text_form"):
            typed_query = st.text_area(
                "의사 질문",
                value=st.session_state.query if st.session_state.get('input_mode') == 'text' else '',
                placeholder="예: 어디가 제일 아프세요?",
                height=76,
            )
            text_search = st.form_submit_button("키워드 추천", type="primary")
        if text_search:
            user_query = typed_query
            search_clicked = True
            st.session_state.input_mode = 'text'
    else:
        q_sorted = questions_df.sort_values(['stage', 'category', 'question_id'])
        q_labels = [
            f"[{r.question_id}] [{r.stage} / {r.category}] {r.question}"
            for r in q_sorted.itertuples()
        ]
        q_text_map = {lbl: row.question for lbl, row in zip(q_labels, q_sorted.itertuples())}
        with st.form("step1_list_form"):
            chosen_label = st.selectbox("질문 목록", options=["(선택)"] + q_labels, index=0)
            list_search = st.form_submit_button("키워드 추천", type="primary")
        if list_search:
            if chosen_label == "(선택)":
                st.markdown('<div class="notice warn">질문을 선택해 주세요.</div>', unsafe_allow_html=True)
            else:
                user_query = q_text_map[chosen_label]
                search_clicked = True
                st.session_state.input_mode = 'list'

    if search_clicked and user_query.strip():
        with st.spinner("추천 중..."):
            match = retrieve_qa(user_query.strip(), q_model, q_embeddings, bm25, questions_df)
        st.session_state.match = match
        st.session_state.query = user_query.strip()
        st.session_state.step = 1
        st.session_state.answers = None
        st.session_state.glosses = None

    if st.session_state.match:
        match = st.session_state.match
        ai_stage = match['stage']
        ai_category = match['category']
        ai_qid = match['question_id']
        ai_question = match['question']
        evidence = match.get('evidence', [])
        ev_txt = ", ".join(evidence) if evidence else "없음"

        st.markdown(f"""
<div class="card">
  <div class="card-title">1. 질문 분류</div>
  <div class="kv">
    <div><strong>의사 질문:</strong> {hx(st.session_state.query)}</div>
    <div><strong>모델 예측:</strong> {hx(ai_stage)} / {hx(ai_category)}</div>
    <div><strong>매칭 질문:</strong> {hx(ai_qid)} · {hx(ai_question)}</div>
    <div><strong>판단 근거:</strong> BM25 {match['bm25_score']:.3f} · BERT {match['bert_score']*100:.1f}% · 공통 키워드 {hx(ev_txt)}</div>
  </div>
</div>
""", unsafe_allow_html=True)

        all_stages = sorted(df['stage'].unique().tolist())
        stage_idx = all_stages.index(ai_stage) if ai_stage in all_stages else 0
        with st.form("step1_confirm_form"):
            col1, col2 = st.columns(2)
            with col1:
                sel_stage = st.selectbox("문진단계", options=all_stages, index=stage_idx)
            with col2:
                cats_for_stage = sorted(df[df['stage'] == sel_stage]['category'].unique().tolist())
                cat_idx = cats_for_stage.index(ai_category) if ai_category in cats_for_stage else 0
                sel_cat = st.selectbox("세부분류", options=cats_for_stage, index=cat_idx)
            confirm_btn = st.form_submit_button("이 분류로 다시 실행", type="primary")
        st.markdown('<div class="card-note">분류를 바꾸면 답변 pool과 표제어가 함께 바뀝니다.</div>',
                    unsafe_allow_html=True)

        if confirm_btn:
            with st.spinner("다시 실행 중..."):
                if sel_stage == ai_stage and sel_category_matches(sel_cat, ai_category, df, ai_qid):
                    final_qid = ai_qid
                else:
                    sub_df = df[(df['stage'] == sel_stage) & (df['category'] == sel_cat)]
                    sub_qs = sub_df.drop_duplicates('question_id')[
                        ['question_id', 'question', 'unique_question']
                    ].reset_index(drop=True)
                    if sub_qs.empty:
                        final_qid = ai_qid
                    else:
                        sub_embs = q_model.encode(sub_qs['unique_question'].tolist(),
                                                  show_progress_bar=False).astype(np.float32)
                        q_emb_tmp = q_model.encode([st.session_state.query],
                                                   show_progress_bar=False).astype(np.float32)
                        sims = cosine_similarity(q_emb_tmp, sub_embs)[0]
                        final_qid = sub_qs.iloc[int(np.argmax(sims))]['question_id']

                answers = df[df['question_id'] == final_qid][
                    ['answer_id', 'answer', 'keyword_sl', 'keyword_ko']
                ].copy()
                answers = answers[answers['answer'].str.strip() != ''].reset_index(drop=True)
                query_emb = q_model.encode(
                    [st.session_state.query], show_progress_bar=False
                ).astype(np.float32)
                per_answer = recommend_glosses_per_answer(
                    answers, q_model, gloss_model, gloss_df, g_embeddings,
                    kiwi=kiwi,
                    question_text=df[df['question_id'] == final_qid]['question'].iloc[0],
                    query_emb=query_emb,
                )
            st.session_state.answers = answers
            st.session_state.per_answer = per_answer
            st.session_state.final_qid = final_qid
            st.session_state.sel_stage = sel_stage
            st.session_state.sel_cat = sel_cat
            st.session_state.step = 2
            st.rerun()

    if st.session_state.step == 2 and st.session_state.answers is not None:
        final_qid = st.session_state.final_qid
        sel_stage = st.session_state.sel_stage
        sel_cat = st.session_state.sel_cat
        final_q = df[df['question_id'] == final_qid]['question'].iloc[0]
        per_answer = st.session_state.get('per_answer', [])

        exact_total = 0
        pool_html = []
        table_rows = []
        row_i = 0
        for item in per_answer:
            exact_gs = [g for g in item['glosses'] if g['match_type'] == 'exact']
            exact_total += len(exact_gs)
            core_html = _gloss_pills(exact_gs, 'rank')
            sl = item['keyword_sl']
            ko = item['keyword_ko']
            meta_bits = [f"유사도 {item['query_sim']*100:.1f}%"]
            if sl and sl != 'nan':
                meta_bits.append(f"수어 {hx(sl)}")
            if ko and ko != 'nan':
                meta_bits.append(f"자연어 {hx(ko)}")
            pool_html.append(
                f'<div class="pool-item">{hx(item["answer"])}{core_html}'
                f'<div class="pool-meta">{" · ".join(meta_bits)}</div></div>'
            )
            for g in exact_gs:
                row_i += 1
                table_rows.append(
                    f'<tr><td class="row-number">{row_i}</td>'
                    f'<td class="gl">{hx(g["gloss"])}</td>'
                    f'<td>{hx(g["rank"])}</td>'
                    f'<td>{hx(item["answer"])}</td></tr>'
                )

        st.markdown(f"""
<div class="card">
  <div class="result-head">
    <span class="result-label">환자 예상 답변 Pool ({len(per_answer)}개)</span>
    <span class="result-meta">{hx(sel_stage)} · {hx(sel_cat)} · {hx(final_qid)}</span>
  </div>
  <div class="kv" style="margin-bottom:12px"><div><strong>의사 질문:</strong> {hx(final_q)}</div></div>
  <div class="pool-list">{''.join(pool_html) if pool_html else '<div class="empty-note">답변 후보 없음</div>'}</div>
  <div class="card-note">표제어는 이 답변들의 직접 일치 키워드에서만 나옵니다.</div>
</div>
""", unsafe_allow_html=True)

        table_body = ''.join(table_rows) or '<tr><td colspan="4">직접 일치 표제어 없음</td></tr>'
        st.markdown(f"""
<div class="card">
  <div class="card-title">핵심 표제어 ({exact_total}개)</div>
  <div class="table-scroll"><table class="table">
    <thead><tr><th>#</th><th>표제어</th><th>인덱스</th><th>근거 문장</th></tr></thead>
    <tbody>{table_body}</tbody>
  </table></div>
</div>
""", unsafe_allow_html=True)

        if st.button("새 질문 입력하기", type="secondary"):
            _reset_query()
            st.rerun()

# ════════════════════════════════════════════════════════════
# API 테스트  (index.html 입력 + JSON 패널)
# ════════════════════════════════════════════════════════════
else:
    if 'api_question' not in st.session_state:
        st.session_state.api_question = ''
    if 'api_top_k' not in st.session_state:
        st.session_state.api_top_k = 5
    if 'api_output' not in st.session_state:
        st.session_state.api_output = None

    st.markdown('<div class="card-title">API 질문</div>', unsafe_allow_html=True)
    st.text_area("의사 질문", placeholder="예: 허리가 아파요", height=76, key="api_question")
    a1, a2 = st.columns([1, 3])
    with a1:
        st.slider("최대 답변 수", 1, 10, key="api_top_k")
    api_submit = st.button("키워드 추천", type="primary", key="api_run_btn")

    if api_submit and st.session_state.api_question.strip():
        with st.spinner("추천 중..."):
            import time as _time
            _t0 = _time.time()
            _q = st.session_state.api_question.strip()
            _k = st.session_state.api_top_k
            api_match = retrieve_qa(_q, q_model, q_embeddings, bm25, questions_df)
            api_answers_df = df[df['question_id'] == api_match['question_id']][
                ['answer_id', 'answer', 'keyword_sl', 'keyword_ko']
            ].copy()
            api_answers_df = api_answers_df[
                api_answers_df['answer'].str.strip() != ''
            ].reset_index(drop=True).head(_k)
            api_results = recommend_top1_per_word(
                api_answers_df, gloss_model, gloss_df, g_embeddings, kiwi,
                question_text=_q,
            )
            st.session_state.api_output = {
                'question': _q,
                'match': api_match,
                'results': api_results,
                'elapsed_ms': round((_time.time() - _t0) * 1000, 1),
            }

    out = st.session_state.api_output
    if out:
        import json as _json
        m = out['match']
        response_json = {
            "question": out['question'],
            "stage": m['stage'],
            "category": m['category'],
            "elapsed_ms": out['elapsed_ms'],
            "answers": [
                {
                    "answer": item["answer"],
                    "glosses": [
                        (f"{kw['gloss']}_{kw.get('origin','')}", kw['score'])
                        for kw in item["keywords"] if kw['match_type'] == 'exact'
                    ],
                }
                for item in out['results']
            ],
        }
        pool_bits = []
        for item in out['results']:
            exact_kws = [k for k in item['keywords'] if k['match_type'] == 'exact']
            pills = _gloss_pills(exact_kws, 'origin')
            pool_bits.append(
                f'<div class="pool-item"><div>{hx(item["answer"])}</div>{pills}</div>'
            )

        json_html = (
            hx(_json.dumps(response_json, ensure_ascii=False, indent=2))
            .replace(' ', '&nbsp;')
            .replace('\n', '<br>')
        )
        st.markdown(f"""
<div class="card">
  <div class="result-head">
    <span class="result-label">핵심 표제어 {sum(len([k for k in i["keywords"] if k["match_type"]=="exact"]) for i in out["results"])}개</span>
    <span class="result-meta">{hx(m['stage'])} · {hx(m['category'])} · {out['elapsed_ms']}ms</span>
  </div>
  <div class="kv" style="margin-bottom:12px">
    <div><strong>질문:</strong> {hx(out['question'])}</div>
    <div><strong>문진단계 / 세부분류:</strong> {hx(m['stage'])} / {hx(m['category'])}</div>
  </div>
  <div class="result-section-title">답변별 표제어</div>
  <div class="pool-list">{''.join(pool_bits)}</div>
  <div class="result-section-title json-title">도출된 결과 JSON</div>
  <details class="json-panel" open>
    <summary>결과 JSON</summary>
    <pre>{json_html}</pre>
  </details>
</div>
""", unsafe_allow_html=True)

# catalog.html 의 전체 현황 카드
st.markdown(f"""
<div class="card">
  <div class="card-title">전체 현황</div>
  <div class="stat-grid">
    <div class="stat-card"><span>전체 Q&amp;A</span><strong>{len(df):,}</strong><small>행</small></div>
    <div class="stat-card"><span>고유 질문</span><strong>{len(questions_df):,}</strong><small>개</small></div>
    <div class="stat-card"><span>중복 정제</span><strong>{dup_n}</strong><small>건</small></div>
    <div class="stat-card"><span>문진단계</span><strong>{df['stage'].nunique()}</strong><small>개</small></div>
    <div class="stat-card"><span>세부분류</span><strong>{df['category'].nunique()}</strong><small>개</small></div>
    <div class="stat-card"><span>글로스</span><strong>{len(gloss_df):,}</strong><small>개</small></div>
  </div>
  <div class="card-note">Q 검색 BM25 60% + BERT 40% · 표제어는 직접 일치만 표시 · 글로스 모델 ko-sroberta</div>
</div>
""", unsafe_allow_html=True)

