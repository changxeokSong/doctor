"""
통증의학과 Q&A REST API  (FastAPI + uvicorn)

실행:
    pip install fastapi uvicorn
    python -m uvicorn api:app --host 0.0.0.0 --port 8502 --reload

엔드포인트:
    POST /query   - 질문 → 답변별 단어 top-1 글로스
    GET  /health  - 서버 상태 확인
"""

from __future__ import annotations
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import numpy as np
from kiwipiepy import Kiwi

from core import (
    load_data, load_st_model, build_question_embeddings,
    build_gloss_embeddings, build_bm25, retrieve_qa,
    recommend_top1_per_word,
    DEFAULT_Q_MODEL, GLOSS_MODEL_NAME,
)

# ─────────────────────────────────────────────────────────────────────
# 전역 상태 (startup 때 한 번 로드)
# ─────────────────────────────────────────────────────────────────────
state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[API] 데이터 및 모델 로딩 중...")
    t0 = time.time()

    df, gloss_df = load_data()
    kiwi         = Kiwi()
    q_model      = load_st_model(DEFAULT_Q_MODEL)
    gloss_model  = load_st_model(GLOSS_MODEL_NAME)

    questions_df = df.drop_duplicates('question_id')[
        ['question_id', 'question', 'unique_question', 'stage', 'category']
    ].reset_index(drop=True)

    q_embeddings = build_question_embeddings(
        q_model, questions_df['unique_question'].tolist()
    )
    g_embeddings = build_gloss_embeddings(
        gloss_model, gloss_df['gloss'].tolist()
    )
    bm25 = build_bm25(questions_df['unique_question'].tolist())

    state.update({
        'df': df, 'gloss_df': gloss_df, 'kiwi': kiwi,
        'q_model': q_model, 'gloss_model': gloss_model,
        'questions_df': questions_df,
        'q_embeddings': q_embeddings, 'g_embeddings': g_embeddings,
        'bm25': bm25,
    })
    print(f"[API] 준비 완료 ({time.time() - t0:.1f}s)")
    yield
    state.clear()


# ─────────────────────────────────────────────────────────────────────
# 앱 생성
# ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="통증의학과 Q&A API",
    description="질문을 입력하면 관련 답변과 답변별 수어 글로스(단어 top-1)를 반환합니다.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────
# 스키마
# ─────────────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question: str
    top_k_answers: int = 5

class AnswerItem(BaseModel):
    answer:  str
    # [("{gloss}_{origin}", score), ...]
    glosses: list[tuple[str, float]]

class QueryResponse(BaseModel):
    question:   str
    stage:      str
    category:   str
    elapsed_ms: float
    answers:    list[AnswerItem]


# ─────────────────────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "model": DEFAULT_Q_MODEL}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="질문을 입력하세요.")

    t0 = time.time()
    df           = state['df']
    gloss_df     = state['gloss_df']
    kiwi         = state['kiwi']
    q_model      = state['q_model']
    gloss_model  = state['gloss_model']
    questions_df = state['questions_df']
    q_embeddings = state['q_embeddings']
    g_embeddings = state['g_embeddings']
    bm25         = state['bm25']

    # 1. BM25 + BERT 하이브리드 질문 매칭
    match = retrieve_qa(
        req.question, q_model, q_embeddings, bm25, questions_df
    )

    # 2. 답변 조회
    answers_df = df[df['question_id'] == match['question_id']][
        ['answer_id', 'answer', 'keyword_sl', 'keyword_ko']
    ].copy()
    answers_df = answers_df[answers_df['answer'].str.strip() != ''].reset_index(drop=True)

    # 4. 단어별 top-1 글로스
    per_word = recommend_top1_per_word(
        answers_df, gloss_model, gloss_df, g_embeddings, kiwi,
        question_text=req.question,
    )

    # 5. 응답 조립: 글로스를 ("{gloss}_{origin}", score) 튜플로 변환
    answer_items = []
    for item in per_word[:req.top_k_answers]:
        glosses = [
            (f"{kw['gloss']}_{kw['origin']}", round(kw['score'], 4))
            for kw in item['keywords']
        ]
        answer_items.append(AnswerItem(
            answer  = item['answer'],
            glosses = glosses,
        ))

    return QueryResponse(
        question   = req.question,
        stage      = match['stage'],
        category   = match['category'],
        elapsed_ms = round((time.time() - t0) * 1000, 1),
        answers    = answer_items,
    )
