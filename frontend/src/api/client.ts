// /api는 vite.config.ts(dev)/nginx(prod)가 백엔드로 프록시하므로 상대경로만 쓰면 된다.
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
  // 표제어 유사도 전체 랭킹은 카드를 펼칠 때 gloss()로 지연 요청한다(응답 크기 폭증 방지).
  runPipeline: (question: string, embModel: string, similarityThreshold: number) =>
    postJSON<PipelineResult>('/pipeline/', {
      question,
      emb_model: embModel,
      similarity_threshold: similarityThreshold,
    }),

  // top_k=1000으로 사실상 사전 전체 랭킹을 받는다.
  gloss: (keyword: string, embModel: string) =>
    postJSON<GlossApiResult>('/gloss/', { keywords: [keyword], top_k: 1000, emb_model: embModel }),

  embeddingModels: () => getJSON<EmbeddingModelsResult>('/embedding-models/'),

  examples: (n = 5) => getJSON<{ examples: string[] }>(`/examples/?n=${n}`),

  glossDictionary: () => getJSON<GlossDictionaryResult>('/gloss-dictionary/'),
}
