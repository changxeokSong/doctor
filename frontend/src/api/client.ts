// /api는 vite.config.ts(dev)/nginx(prod)가 백엔드로 프록시하므로 상대경로만 쓰면 된다.
import type { PipelineResult, EmbeddingModelsResult, GlossApiResult, GlossDictionaryResult } from './types'

export class ApiError extends Error {  // status: main.tsx retry 로직이 4xx/5xx 구분용
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// HTML 500 에러 페이지 전체가 화면에 덤프되지 않도록 JSON이면 그대로, 아니면 앞부분만 자른다.
async function toApiError(path: string, res: Response): Promise<ApiError> {
  const text = await res.text()
  try {
    return new ApiError(`${path} 요청 실패 (${res.status}): ${JSON.stringify(JSON.parse(text))}`, res.status)
  } catch {
    return new ApiError(`${path} 요청 실패 (${res.status}): ${text.slice(0, 200)}`, res.status)
  }
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await toApiError(path, res)
  return res.json()
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) throw await toApiError(path, res)
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
