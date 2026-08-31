// Django 백엔드 호출부. Vite 개발 서버가 /api를 :8000으로 프록시하므로 상대경로만 쓰면 된다
// (vite.config.ts 참고).
import type { PipelineResult, EmbeddingModelsResult, GlossApiResult, GlossDictionaryResult } from './types'

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`${path} 요청 실패 (${res.status}): ${await res.text()}`)
  }
  return res.json()
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) {
    throw new Error(`${path} 요청 실패 (${res.status}): ${await res.text()}`)
  }
  return res.json()
}

export const api = {
  // 키워드 추출 방식을 고를 파라미터는 없다(백엔드가 대표 키워드 1개 방식으로 고정, services.py
  // 참고). KoBART 생성 폴백도 코드째 삭제돼(ISSUE-64) show_generation 파라미터가 없고, 답변 소스가
  // 검색(retriever) 하나뿐이라 show_retrieval 토글도 없다. 표제어 매핑은 여기서는 정확일치 여부만
  // 오고, 유사도 전체 랭킹은 카드를 펼칠 때 아래 gloss()로 따로 지연 요청한다(2026-08-19 — 답변마다
  // 미리 다 계산해 넣었다가 응답이 최대 ~900KB까지 커져 서버 디스크를 채운 장애 이후 변경).
  runPipeline: (question: string, embModel: string, similarityThreshold: number) =>
    postJSON<PipelineResult>('/pipeline/', {
      question,
      emb_model: embModel,
      similarity_threshold: similarityThreshold,
    }),

  // 답변 카드를 펼쳤을 때 그 키워드 하나에 대해서만 사전 전체(~654개) 유사도 랭킹을 가져온다
  // (top_k를 넉넉히 큰 값으로 줘서 사실상 "전체"를 받는다 — 백엔드 GlossRequestSerializer의
  // max_value=1000 참고).
  gloss: (keyword: string, embModel: string) =>
    postJSON<GlossApiResult>('/gloss/', { keywords: [keyword], top_k: 1000, emb_model: embModel }),

  embeddingModels: () => getJSON<EmbeddingModelsResult>('/embedding-models/'),

  examples: (n = 5) => getJSON<{ examples: string[] }>(`/examples/?n=${n}`),

  // 표제어 사전 전체(654개) + 카테고리 통계 - "이 단어 왜 없냐"는 질문에 바로 답할 수 있게
  // 투명하게 보여주는 페이지용(2026-08-26).
  glossDictionary: () => getJSON<GlossDictionaryResult>('/gloss-dictionary/'),
}
