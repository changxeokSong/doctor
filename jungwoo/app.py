import os
import re
import warnings
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

# Streamlit의 hot-reload 감시자(local_sources_watcher.py)가 매 rerun마다 sys.modules를 훑으며
# __path__를 건드리는데, 이때 torchaudio의 지연 백엔드 디스패치가 self-warning을 던진다(우리 코드는
# torchaudio를 직접 쓰지 않음 - torch/sentence-transformers가 끌고 들어온 간접 의존성일 뿐이라
# 무해한 경고다). 위 with-block과 달리 이건 import 시점이 아니라 매 rerun마다 반복되므로 전역
# 필터로 계속 억제해야 로그가 안 쌓인다.
warnings.filterwarnings("ignore", message="Torchaudio's I/O functions now support")

# ────────────────────────────────────────────────────────────
# 파일 경로
# ────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_files     = os.listdir(BASE_DIR)
EXCEL_FILE = os.path.join(BASE_DIR, next(f for f in _files if '0528' in f))
GLOSS_FILE = os.path.join(BASE_DIR, 'etri_glosses.csv')

# ────────────────────────────────────────────────────────────
# 선택 가능한 Q 검색 모델 목록
# 2026-08-10(ISSUE-93): 라벨에 파라미터 수 표기 추가(HuggingFace Hub 기준 실측치) — DGX Spark
# 이전 후 GPU 메모리 예산 확인용. 이 5종 중 SAP-BERT-Ko-En·KM-BERT·ko-sroberta는 app/config.py의
# EMB_MODEL_OPTIONS와 겹치고(같은 가중치 재사용), MiniLM·Medical Bi-Encoder Q는 jungwoo 전용이다.
# ────────────────────────────────────────────────────────────
AVAILABLE_MODELS = {
    "jhgan/ko-sroberta-multitask":                                   "Ko-SRoBERTa (기본, 한국어 STS, 약 110M)",
    "snumin44/sap-bert-ko-en":                                       "SAP-BERT Ko-En (의료 특화, 약 111M)",
    "madatnlp/km-bert":                                              "KM-BERT (한국어 의료 특화, MedSTS, 약 99M)",
    "snumin44/medical-biencoder-ko-bert-question":                   "Medical Bi-Encoder Q (의료 QA 특화, 약 111M)",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2":  "Multilingual MiniLM (다국어, 약 118M)",
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

    gloss_df = pd.read_csv(GLOSS_FILE, encoding='utf-8-sig')
    gloss_df['gloss'] = gloss_df['gloss'].fillna('').astype(str).str.strip()
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
def build_gloss_embeddings(_model, glosses: tuple, model_name: str):
    """SAP-BERT로 글로스 임베딩 생성. 접두어로 의료 문맥 부여."""
    prefixed = [f"의료 수어 표제어: {g}" for g in glosses]
    return _model.encode(prefixed, batch_size=256,
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

        def token_match(g: str, tokens: set, full: str) -> bool:
            """
            형태소 기반 + 조사 처리 통합 매칭.
            1) Kiwi 형태소 집합에 정확히 포함 (기본형 매칭: '아픈'→'아프다')
            2) 공백 분리 토큰이 글로스로 시작 (조사 처리: '고혈압이'→'고혈압')
            3) 복합어 글로스: 원문 substring
            최소 2자 이상.
            """
            if len(g) < 2:
                return False
            g_words = re.sub(r'[^\w가-힣a-zA-Z0-9]', ' ', g).split()
            if len(g_words) == 1:
                # 형태소 기본형에서 정확 매칭
                if g in tokens:
                    return True
                # 공백 토큰 startswith (조사 보완)
                return any(tok.startswith(g) for tok in space_tokens)
            else:
                return g in full

        # ── 1순위: 단어 직접 일치 + 동음이의어 검증 ──
        exact = []
        for j, g in enumerate(gloss_list):
            if not g:
                continue
            if not token_match(g, word_tokens, full_text):
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
            if not token_match(g, kw_sl_tokens, kw_sl_text):
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
    page_icon="🏥",
    layout="wide",
)

st.title("🏥 통증의학과 초진 Q&A 답변 검색")
st.markdown(
    "질문을 입력하면 **문진 단계·세부 분류를 자동으로 파악**하고, "
    "RAG로 답변을 찾은 뒤 SAP-BERT 의료 유사도로 **추천 글로스**를 제시합니다."
)

# ── 사이드바 ──
with st.sidebar:
    st.header("⚙️ 모델 설정")

    # ── Q 검색 모델 선택 드롭다운 ──
    sel_model_name = st.selectbox(
        "Q 검색 모델",
        options=list(AVAILABLE_MODELS.keys()),
        format_func=lambda k: AVAILABLE_MODELS[k],
        key="model_selector",
        help="질문 유사도 검색에 사용할 BERT 모델을 선택합니다.",
    )

    # 모델이 변경되면 임베딩 캐시 무효화 + 세션 초기화
    if st.session_state.get("_active_model") != sel_model_name:
        st.session_state["_active_model"] = sel_model_name
        for key in ['step', 'match', 'answers', 'glosses',
                    'query', 'final_qid', 'sel_stage', 'sel_cat',
                    'per_answer', 'input_mode']:
            st.session_state.pop(key, None)

    st.caption(f"**글로스 모델:** ko-sroberta (문장 유사도 특화, 고정)")
    st.divider()

    st.header("📊 데이터 현황")

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
)
bm25 = build_bm25(tuple(questions_df['unique_question'].tolist()))

with st.sidebar:
    st.metric("전체 Q&A 행", f"{len(df):,}")
    st.metric("고유 질문 수", f"{len(questions_df):,}")
    st.metric("중복 질문 정제", f"{(questions_df['unique_question'] != questions_df['question']).sum()}건")
    st.metric("문진 단계 수", f"{df['stage'].nunique()}")
    st.metric("세부 분류 수", f"{df['category'].nunique()}")
    st.metric("ETRI 글로스 수", f"{len(gloss_df):,}")
    st.divider()

    # 검색 결과 스코어
    if st.session_state.get('match'):
        m = st.session_state.match
        st.header("🎯 검색 스코어")
        st.metric("BM25 점수", f"{m['bm25_score']:.3f}",
                  help="단어 키워드 매칭 점수 (0~1, 정규화)")
        st.metric("BERT 유사도", f"{m['bert_score']*100:.1f}%",
                  help="의미 유사도 (코사인 유사도)")
        st.metric("하이브리드 점수", f"{m['similarity']:.3f}",
                  help="BM25 60% + BERT 40% 가중합산")
        st.divider()

    st.caption(f"Q 검색: BM25(60%) + BERT(40%) 하이브리드 RAG")
    st.caption(f"글로스: ko-sroberta 문장 유사도 (임계값 ≥ {BERT_SIM_THRESHOLD})")

st.divider()

# ── session_state 초기화 ──
for key, default in {
    'step':     1,
    'match':    None,
    'answers':  None,
    'glosses':  None,
    'query':    '',
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ══════════════════════════════════════════════
# STEP 1 — 질문 입력 + AI 추천 분류 확인
# ══════════════════════════════════════════════
st.markdown("### Step 1 · 질문 입력 및 분류 확인")

input_tab_text, input_tab_list = st.tabs(["✏️ 직접 입력", "📋 목록에서 선택"])

user_query     = ""
search_clicked = False

with input_tab_text:
    with st.form("step1_text_form"):
        typed_query = st.text_input(
            "질문을 입력하세요",
            value=st.session_state.query if st.session_state.get('input_mode') == 'text' else '',
            placeholder="예: 통증이 언제부터 시작됐나요? / 어떤 자세에서 더 아프세요?",
        )
        text_search = st.form_submit_button("🔍 AI 분류 추천받기", type="primary")
    if text_search:
        user_query     = typed_query
        search_clicked = True
        st.session_state.input_mode = 'text'

with input_tab_list:
    q_sorted = questions_df.sort_values(['stage', 'category', 'question_id'])
    q_labels = [
        f"[{r.question_id}] [{r.stage} / {r.category}] {r.question}"
        for r in q_sorted.itertuples()
    ]
    q_text_map = {lbl: row.question for lbl, row in zip(q_labels, q_sorted.itertuples())}

    with st.form("step1_list_form"):
        chosen_label = st.selectbox(
            "질문을 선택하세요",
            options=["(선택)"] + q_labels,
            index=0,
        )
        list_search = st.form_submit_button("🔍 AI 분류 추천받기", type="primary")
    if list_search:
        if chosen_label == "(선택)":
            st.warning("질문을 선택해 주세요.")
        else:
            user_query     = q_text_map[chosen_label]
            search_clicked = True
            st.session_state.input_mode = 'list'

if search_clicked and user_query.strip():
    with st.spinner("BM25 + BERT 하이브리드로 분석 중..."):
        match = retrieve_qa(user_query.strip(), q_model, q_embeddings, bm25, questions_df)
    st.session_state.match   = match
    st.session_state.query   = user_query.strip()
    st.session_state.step    = 1
    st.session_state.answers = None
    st.session_state.glosses = None

# ── AI 추천 결과 + 사람 검토 드롭다운 ──
if st.session_state.match:
    match       = st.session_state.match
    ai_stage    = match['stage']
    ai_category = match['category']
    ai_qid      = match['question_id']
    ai_question = match['question']
    evidence    = match.get('evidence', [])

    st.markdown("#### 🤖 1차 분류 결과")

    card1, card2, card3 = st.columns(3)

    with card1:
        with st.container(border=True):
            st.caption("① 의사 질문")
            st.markdown(f"`{ai_qid}`")
            st.markdown(f"**{ai_question}**")

    with card2:
        with st.container(border=True):
            st.caption("② 문진 단계 및 세부 분류")
            st.markdown(f"**문진 단계** &nbsp; `{ai_stage}`")
            st.markdown(f"**세부 분류** &nbsp; `{ai_category}`")

    with card3:
        with st.container(border=True):
            st.caption("③ 근거")
            st.markdown(f"**BM25** `{match['bm25_score']:.3f}` &nbsp; **BERT** `{match['bert_score']*100:.1f}%`")
            if evidence:
                st.markdown("공통 키워드: " + "  ".join([f"`{w}`" for w in evidence]))
            else:
                st.caption("공통 키워드 없음")

    st.divider()
    st.markdown("#### ✏️ 분류 검토 및 수정")
    st.caption("AI 추천값이 기본 선택되어 있습니다. 틀렸다면 직접 변경 후 확인하세요.")

    all_stages = sorted(df['stage'].unique().tolist())
    stage_idx  = all_stages.index(ai_stage) if ai_stage in all_stages else 0

    with st.form("step1_confirm_form"):
        col1, col2 = st.columns(2)
        with col1:
            sel_stage = st.selectbox("문진 단계", options=all_stages, index=stage_idx)
        with col2:
            cats_for_stage = sorted(df[df['stage'] == sel_stage]['category'].unique().tolist())
            cat_idx = cats_for_stage.index(ai_category) if ai_category in cats_for_stage else 0
            sel_cat = st.selectbox("세부 분류", options=cats_for_stage, index=cat_idx)

        confirm_btn = st.form_submit_button("✅ 확인 — 답변/표제어 생성", type="primary")

    if confirm_btn:
        with st.spinner("답변 및 글로스 생성 중..."):
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
                    sub_embs  = q_model.encode(sub_qs['unique_question'].tolist(),
                                               show_progress_bar=False).astype(np.float32)
                    q_emb_tmp = q_model.encode([st.session_state.query],
                                               show_progress_bar=False).astype(np.float32)
                    sims      = cosine_similarity(q_emb_tmp, sub_embs)[0]
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

        st.session_state.answers    = answers
        st.session_state.per_answer = per_answer
        st.session_state.final_qid  = final_qid
        st.session_state.sel_stage  = sel_stage
        st.session_state.sel_cat    = sel_cat
        st.session_state.step       = 2
        st.rerun()

# ══════════════════════════════════════════════
# STEP 2 — 답변 목록 + 글로스
# ══════════════════════════════════════════════
if st.session_state.step == 2 and st.session_state.answers is not None:
    final_qid = st.session_state.final_qid
    sel_stage = st.session_state.sel_stage
    sel_cat   = st.session_state.sel_cat

    st.divider()
    st.markdown("### Step 2 · 답변 목록")

    final_q = df[df['question_id'] == final_qid]['question'].iloc[0]
    tag_cols = st.columns(3)
    tag_cols[0].markdown(f"**문진 단계:** `{sel_stage}`")
    tag_cols[1].markdown(f"**세부 분류:** `{sel_cat}`")
    tag_cols[2].markdown(f"**질문 ID:** `{final_qid}`")
    st.success(f"**질문:** {final_q}")

    per_answer = st.session_state.get('per_answer', [])

    if not per_answer:
        st.warning("등록된 답변이 없습니다.")
    else:
        st.caption(f"총 {len(per_answer)}개 답변 (질문 유사도 높은 순)")
        for item in per_answer:
            with st.container(border=True):
                head_col, sim_col = st.columns([5, 1])
                with head_col:
                    st.markdown(f"**▸ `{item['answer_id']}`** &nbsp; {item['answer']}")
                with sim_col:
                    st.metric("유사도", f"{item['query_sim']*100:.1f}%")

                sl = item['keyword_sl']
                ko = item['keyword_ko']
                if (sl and sl != 'nan') or (ko and ko != 'nan'):
                    meta = st.columns(2)
                    if sl and sl != 'nan':
                        meta[0].caption(f"✋ 수어 키워드: {sl}")
                    if ko and ko != 'nan':
                        meta[1].caption(f"💬 자연어: {ko}")

                with st.expander("▼ 표제어(글로스) 보기"):
                    gs = item['glosses']
                    if not gs:
                        st.caption("매칭되는 표제어 없음")
                    else:
                        gcols = st.columns(len(gs))
                        for col, g in zip(gcols, gs):
                            if g['match_type'] == 'exact':
                                label = f"🔤 직접 일치 | #{g['rank']}"
                                delta = f"매칭: {g['best_word']}"
                            elif g['match_type'] == 'keyword':
                                label = f"🔑 수어 키워드 | #{g['rank']}"
                                delta = f"키워드: {g['best_word']}"
                            else:
                                label = f"🏥 {g['similarity']*100:.1f}% | #{g['rank']}"
                                delta = "의료 문맥 유사도"
                            col.metric(label=label, value=g['gloss'], delta=delta)

    st.divider()
    if st.button("🔄 새 질문 입력하기"):
        for key in ['step', 'match', 'answers', 'glosses', 'query',
                    'final_qid', 'sel_stage', 'sel_cat', 'per_answer']:
            st.session_state.pop(key, None)
        st.rerun()
