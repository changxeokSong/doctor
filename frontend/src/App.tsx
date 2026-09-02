import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api/client'
import type { PipelineResult, RecentOutputEntry } from './api/types'
import { usePersistedState } from './hooks/usePersistedState'
import { QuestionInput } from './components/QuestionInput'
import { RecommendedGlossesTable, RecommendationStats, ResultJsonViewer } from './components/CandidatesPanel'
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

type View = 'main' | 'dictionary' | 'analysis'

function MainApp() {
  const [question, setQuestion] = useState('')
  const [embModel, setEmbModel] = usePersistedState<string>('embModel', '', (v) => typeof v === 'string')
  const [similarityThreshold, setSimilarityThreshold] = usePersistedState(
    'similarityThreshold', 0.65, (v) => typeof v === 'number' && v >= 0 && v <= 1,
  )
  const [result, setResult] = useState<PipelineResult | null>(null)
  const [lastRequest, setLastRequest] = useState<{ question: string; emb_model: string; similarity_threshold: number } | null>(null)
  const [view, setView] = usePersistedState<View>('view', 'main', (v) => v === 'main' || v === 'dictionary' || v === 'analysis')
  const [recentOutputs, setRecentOutputs] = usePersistedState<RecentOutputEntry[]>(
    // 옛 스키마로 저장된 캐시가 남아있으면 렌더링 중 크래시하므로 항목 모양까지 검증해 버린다.
    // 필드를 추가할 때마다 여기도 같이 늘려야 타입 선언(비옵셔널)과 실제 저장값이 어긋나지 않는다.
    'recentOutputs', [],
    (v) => Array.isArray(v) && v.every((e) =>
      typeof (e as RecentOutputEntry)?.stage === 'string' &&
      Array.isArray((e as RecentOutputEntry)?.glosses) &&
      (e as RecentOutputEntry).glosses.every((g) =>
        typeof g.keyword === 'string' && typeof g.glossId === 'number' && typeof g.prioritized === 'boolean',
      ),
    ),
  )

  const queryClient = useQueryClient()
  const embModelsQuery = useQuery({ queryKey: ['embedding-models'], queryFn: api.embeddingModels })

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
    onSuccess: (r, q) => {
      setResult(r)
      setLastRequest({ question: q, emb_model: embModel, similarity_threshold: similarityThreshold })
      // 방금 요청으로 embModel이 새로 로드됐을 수 있어 loaded 상태 갱신
      queryClient.invalidateQueries({ queryKey: ['embedding-models'] })
      const entry: RecentOutputEntry = {
        question: q,
        stage: r.top_stage.label,
        subCategory: r.top_sub.label,
        timestamp: Date.now(),
        glosses: r.recommended_glosses.map((g) => ({
          glossId: g.glossId, keyword: g.keyword, score: g.score, source: g.source,
          prioritized: g.prioritized, priorityKind: g.priorityKind,
        })),
      }
      setRecentOutputs([entry, ...recentOutputs].slice(0, 20))
    },
  })

  function runPipeline(q?: string) {
    const target = q ?? question
    if (!target.trim() || !embModel) return
    pipelineMutation.mutate(target)
  }

  // 참고 사이트(163.239.25.74:8777)는 화면 3개(index/catalog/analysis)가 각자 헤더 네비를
  // 갖는데, 우리는 SPA라 상태 토글로 흉내낸다 - 라벨/화살표 위치까지 그쪽과 동일하게 맞춘다.
  const nav = view === 'dictionary'
    ? [{ label: '분석 페이지', onClick: () => setView('analysis') }, { label: '← 추천 화면', onClick: () => setView('main') }]
    : view === 'analysis'
    ? [{ label: '글로스·문진 현황', onClick: () => setView('dictionary') }, { label: '← 추천 화면', onClick: () => setView('main') }]
    : [{ label: '글로스·문진 현황', onClick: () => setView('dictionary') }, { label: '분석 페이지 →', onClick: () => setView('analysis') }]

  return (
    <div className="layout">
      <div className="main">
        <div className="app-header">
          <div>
            <h1>수어 글로스 추천기</h1>
            <p>의사 질문을 입력하면 환자 답변에 쓸 핵심 표제어를 추천합니다.</p>
          </div>
          <nav className="app-nav">
            {nav.map((n) => (
              <button key={n.label} type="button" className="app-link" onClick={n.onClick}>{n.label}</button>
            ))}
          </nav>
        </div>

        {view === 'dictionary' ? (
          <GlossDictionaryPage recentOutputs={recentOutputs} />
        ) : view === 'analysis' ? (
          result ? (
            <>
            {pipelineMutation.isError && (
              <div role="alert" className="notice error">{(pipelineMutation.error as Error).message}</div>
            )}
            <AnalysisPanel
              result={result}
              embOptions={embModelsQuery.data?.options ?? []}
              embModel={embModel} onEmbModelChange={setEmbModel}
              similarityThreshold={similarityThreshold} onSimilarityThresholdChange={setSimilarityThreshold}
              onRerun={runPipeline} rerunning={pipelineMutation.isPending}
            />
            </>
          ) : (
            <div className="card">
              <div className="card-title">실행 기록 없음</div>
              <div className="empty-note">추천 화면에서 질문을 한 번 실행하면 그 결과의 근거가 여기에 표시됩니다.</div>
            </div>
          )
        ) : (
          <>
            {embModelsQuery.isError && (
              <div role="alert" className="notice error">
                임베딩 모델 목록을 불러오지 못했습니다 — 백엔드 서버 상태를 확인해주세요.
              </div>
            )}

            <QuestionInput
              value={question}
              onChange={setQuestion}
              onSubmit={runPipeline}
              loading={pipelineMutation.isPending}
              canSubmit={!!embModel}
            />

            {pipelineMutation.isError && (
              <div role="alert" className="notice error">
                {(pipelineMutation.error as Error).message}
              </div>
            )}

            {result && !result.retrieval_ok && (
              <div className="notice warn">
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

            {result && (
              <div className="card" id="resultCard">
                <div className="result-head">
                  <span className="result-label">핵심 표제어 {result.table_rows.length}개</span>
                  <span className="result-meta">{result.top_stage.label} · {result.top_sub.label}</span>
                </div>
                <RecommendationStats stats={result.stats} />
                <RecommendedGlossesTable
                  rows={result.table_rows} matchedQuestion={result.matched_question}
                />
                <ResultJsonViewer requestBody={lastRequest} resultBody={result.keywords_envelope} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
