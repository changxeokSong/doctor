import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api/client'
import type { PipelineResult } from './api/types'
import { usePersistedState } from './hooks/usePersistedState'
import { QuestionInput } from './components/QuestionInput'
import { RecommendedGlossesTable } from './components/CandidatesPanel'
import { AnalysisPanel } from './components/AnalysisPanel'
import { GlossDictionaryPage } from './components/GlossDictionaryPage'

export default function App() {
  const [path, setPath] = useState(window.location.pathname)

  useEffect(() => {
    const onPopState = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const isDemo1 = path === '/demo1' || path === '/demo1/'

  if (!isDemo1) {
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="max-w-md w-full text-center">
          <div className="flex flex-col gap-3">
            <button
              className="border border-[var(--mh-border)] rounded-md px-4 py-3 text-left hover:bg-[var(--mh-surface-2)]"
              onClick={() => {
                window.history.pushState({}, '', '/demo1')
                setPath('/demo1')
              }}
            >
              <div className="font-semibold">분류 + 임베딩 검색</div>
              <div className="text-sm text-[var(--mh-muted)]">문진 자동분류 → 답변 검색 → 수어 글로스 추천</div>
            </button>
            <button
              className="border border-[var(--mh-border)] rounded-md px-4 py-3 text-left hover:bg-[var(--mh-surface-2)]"
              onClick={() => { window.location.href = '/jungwoo/' }}
            >
              <div className="font-semibold">BM25 하이브리드 검색</div>
              <div className="text-sm text-[var(--mh-muted)]">BM25 + BERT 하이브리드 Q&A 검색</div>
            </button>
          </div>
        </div>
      </div>
    )
  }

  return <MainApp />
}

function MainApp() {
  const [question, setQuestion] = useState('')
  const [embModel, setEmbModel] = usePersistedState<string>('embModel', '', (v) => typeof v === 'string')
  const [similarityThreshold, setSimilarityThreshold] = usePersistedState(
    'similarityThreshold', 0.65, (v) => typeof v === 'number' && v >= 0 && v <= 1,
  )
  const [result, setResult] = useState<PipelineResult | null>(null)
  const [showAnalysis, setShowAnalysis] = usePersistedState('showAnalysis', false, (v) => typeof v === 'boolean')
  const [showDictionary, setShowDictionary] = useState(false)

  const queryClient = useQueryClient()
  const embModelsQuery = useQuery({ queryKey: ['embedding-models'], queryFn: api.embeddingModels })
  const examplesQuery = useQuery({ queryKey: ['examples'], queryFn: () => api.examples(5) })

  useEffect(() => {
    if (!embModelsQuery.data) return
    const known = embModelsQuery.data.options.some((o) => o.model_id === embModel)  // 저장된 값이 폐기된 모델이면 기본값으로
    if (!embModel || !known) {
      setEmbModel(embModelsQuery.data.default_model_id)
    }
  }, [embModelsQuery.data, embModel])

  const pipelineMutation = useMutation({
    mutationFn: (q: string) =>
      api.runPipeline(q, embModel, similarityThreshold),
    onSuccess: (r) => {
      setResult(r)
      // 방금 요청으로 embModel이 새로 로드됐을 수 있어 loaded 상태 갱신
      queryClient.invalidateQueries({ queryKey: ['embedding-models'] })
    },
  })

  function runPipeline(q?: string) {
    const target = q ?? question
    if (!target.trim() || !embModel) return
    pipelineMutation.mutate(target)
  }

  return (
    <div className="min-h-screen flex justify-center px-[18px] py-10">
      <div className="w-full max-w-[880px] flex flex-col gap-[18px]">
        <div className="flex items-baseline justify-between gap-4">
          <div>
            <h1 className="text-[22px] leading-[1.25] font-bold">수어 글로스 추천기</h1>
            <p className="text-[13px] text-[var(--mh-muted)] mt-1">의사 질문을 입력하면 환자 답변에 쓸 핵심 표제어를 추천합니다.</p>
          </div>
          <div className="flex items-center gap-4 shrink-0">
            <button
              type="button"
              className="text-[13px] font-semibold text-[var(--mh-accent)] hover:underline whitespace-nowrap"
              onClick={() => setShowDictionary(!showDictionary)}
            >
              {showDictionary ? '← 추천 화면' : '표제어 사전 →'}
            </button>
            {result && !showDictionary && (
              <button
                type="button"
                className="text-[13px] font-semibold text-[var(--mh-accent)] hover:underline whitespace-nowrap"
                onClick={() => setShowAnalysis(!showAnalysis)}
              >
                {showAnalysis ? '← 추천 화면' : '분석 보기 →'}
              </button>
            )}
          </div>
        </div>

        {showDictionary ? (
          <GlossDictionaryPage />
        ) : (
          <>
            {embModelsQuery.isError && (
              <div role="alert" className="rounded-[10px] px-[15px] py-[13px] text-[13px] leading-[1.6] bg-[#fff1f0] border border-[#ffc1c0] text-[#c0392b]">
                임베딩 모델 목록을 불러오지 못했습니다 — 백엔드 서버 상태를 확인해주세요.
              </div>
            )}

            <QuestionInput
              value={question}
              onChange={setQuestion}
              onSubmit={runPipeline}
              examples={examplesQuery.data?.examples ?? []}
              loading={pipelineMutation.isPending}
              embOptions={embModelsQuery.data?.options ?? []}
              embModel={embModel} onEmbModelChange={setEmbModel}
            />

            {pipelineMutation.isError && (
              <div role="alert" className="rounded-[10px] px-[15px] py-[13px] text-[13px] leading-[1.6] bg-[#fff1f0] border border-[#ffc1c0] text-[#c0392b]">
                {(pipelineMutation.error as Error).message}
              </div>
            )}

            {result && !showAnalysis && !result.retrieval_ok && (
              <div className="rounded-[10px] px-[15px] py-[13px] text-[13px] leading-[1.6] bg-[#fff8e1] border border-[#ffe082] text-[#7a5b0b] mb-3">
                <div>
                  ⚠ 가장 비슷한 기존 질문의 유사도({(result.similarity * 100).toFixed(1)}%)가 설정한
                  임계값({(similarityThreshold * 100).toFixed(1)}%)보다 낮습니다 — 아래 추천은 신뢰도가
                  낮을 수 있습니다.
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs font-bold shrink-0">임계값 조정</span>
                  <input
                    type="range" min={0} max={1} step={0.01}
                    value={similarityThreshold}
                    onChange={(e) => setSimilarityThreshold(Number(e.target.value))}
                    className="flex-1"
                  />
                  <span className="text-xs tabular-nums shrink-0">{(similarityThreshold * 100).toFixed(0)}%</span>
                </div>
              </div>
            )}

            {result && !showAnalysis && (
              <RecommendedGlossesTable
                glosses={result.recommended_glosses} matchedQuestion={result.matched_question}
                answers={result.retrieval_candidates.map((c) => c.answer)}
                stageLabel={result.top_stage.label} subLabel={result.top_sub.label}
                evidenceMinScore={result.evidence_min_score}
              />
            )}

            {result && showAnalysis && (
              <AnalysisPanel
                result={result}
                embOptions={embModelsQuery.data?.options ?? []}
                embModel={embModel} onEmbModelChange={setEmbModel}
                similarityThreshold={similarityThreshold} onSimilarityThresholdChange={setSimilarityThreshold}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}
