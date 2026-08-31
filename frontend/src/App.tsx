import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api/client'
import type { PipelineResult } from './api/types'
import { usePersistedState } from './hooks/usePersistedState'
import { QuestionInput } from './components/QuestionInput'
import { RecommendedGlossesTable } from './components/CandidatesPanel'
import { AnalysisPanel } from './components/AnalysisPanel'
import { GlossDictionaryPage } from './components/GlossDictionaryPage'

// demo1은 실제 URL(/demo1)을 가진 화면이다 — React state 토글이 아니라 진짜 경로 이동이라
// 브라우저 뒤로가기가 자연스럽게 선택 화면(/)으로 돌아간다. demo2(jungwoo)는 완전히 별개 앱이라
// 원래부터 실제 페이지 이동(/jungwoo/)이었다 — 이제 둘 다 같은 방식(실제 주소 이동)으로 통일.
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

// 163.239.25.74:8777(medical_qna_llm/gloss-recommender/public/index.html)의 레이아웃을 그대로
// 옮겼다 - .layout(가운데 정렬) > .main(최대 880px, 세로 flex, gap 18px) > 헤더 + 카드들
// (2026-08-25, 사용자 요청 "이 코드 참고해서 아예 똑같이, 디자인적으로 필요없는거 싹 다 빼고").
// 예전에 왼쪽 사이드바에 있던 임베딩 모델·유사도 임계값 설정은 저쪽 analysis.html의
// "5. 실행 설정"과 같은 자리(분석 패널 맨 아래)로 옮겼다.
function MainApp() {
  const [question, setQuestion] = useState('')
  const [embModel, setEmbModel] = usePersistedState<string>('embModel', '')
  const [similarityThreshold, setSimilarityThreshold] = usePersistedState('similarityThreshold', 0.65)
  const [result, setResult] = useState<PipelineResult | null>(null)
  const [showAnalysis, setShowAnalysis] = usePersistedState('showAnalysis', false)
  // 표제어 사전 전체 목록 페이지 - "이 단어 왜 없냐"에 바로 답할 수 있게(2026-08-26, 사용자 요청).
  // 실제 라우팅 없이 같은 화면 안에서 토글만 하는 이유는 분석 보기와 같은 패턴을 그대로 따른 것.
  const [showDictionary, setShowDictionary] = useState(false)

  const queryClient = useQueryClient()
  const embModelsQuery = useQuery({ queryKey: ['embedding-models'], queryFn: api.embeddingModels })
  const examplesQuery = useQuery({ queryKey: ['examples'], queryFn: () => api.examples(5) })

  useEffect(() => {
    if (embModelsQuery.data && !embModel) {
      setEmbModel(embModelsQuery.data.default_model_id)
    }
  }, [embModelsQuery.data, embModel])

  const pipelineMutation = useMutation({
    mutationFn: (q: string) =>
      api.runPipeline(q, embModel, similarityThreshold),
    onSuccess: (r) => {
      setResult(r)
      // 이번 요청으로 선택된 임베딩 모델이 새로 로드됐을 수 있으니(cold_start), 설정 패널의
      // "로드됨/처음 쓰면 로딩됨" 표시가 최신 상태를 반영하도록 다시 불러온다.
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
              <div className="rounded-[10px] px-[15px] py-[13px] text-[13px] leading-[1.6] bg-[#fff1f0] border border-[#ffc1c0] text-[#c0392b]">
                {(pipelineMutation.error as Error).message}
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
