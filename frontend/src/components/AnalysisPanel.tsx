import type { EmbeddingModelOption, PipelineResult } from '../api/types'

/** 원본 코퍼스 엑셀(통증의학과_초진_의사문의_답변_키워드_이현_0528.xlsx)의 "키워드_선정기준" 시트를
 * 그대로 옮긴 것 - v2(SpanTagger) 학습 라벨(대표 환자키워드)을 사람이 고를 때 쓴 실제 원칙이다
 * (2026-08-19, 사용자가 "엑셀에 있는 기준을 화면에서도 보이게" 요청).*/
const KEYWORD_SELECTION_PRINCIPLES = [
  { title: '핵심 원칙', desc: '답변 문장 안 실제 단어·구를 그대로 선택', example: '앉아 있으면 더 아픕니다. → 앉아 있으면' },
  { title: '일반 서술어 지양', desc: "'아픕니다/있습니다' 단독 선택 지양 — 자세·부위·강도·상태·동작 우선", example: '걸으면 더 아파요. → 걸으면' },
  { title: '동사 포함 가능', desc: '힘 빠짐·저림·부음 등 필요시 동사/상태어 선택', example: '가끔 힘이 빠집니다. → 빠집니다' },
  { title: '예/아니오 문항', desc: '실제 답변의 판단어·구체 상태어 선택', example: '아니요, 저림은 없어요. → 없어요' },
]

/** 조윤기 팀 데모(163.239.25.74:8777, 실제 소스는 medical_qna_llm/gloss-recommender/public/)의
 * "분석 페이지"(질문분류 근거 · 표제어 생성 경로 · 답변 pool · latency breakdown을 한눈에 보여주는
 * 디버그 화면)를 그대로 참고해서 만들었다 - 카드마다 title(.card-title) + 내용(.kv/.field-grid) +
 * 설명(.card-note) 구조, 새 백엔드 로직 없이 이미 파이프라인 응답에 있는 값만 다시 정리해서
 * 보여준다(2026-08-19). 저쪽 5번 "실행 설정"(Provider/Model/Endpoint) 자리에 저희는 임베딩
 * 모델·유사도 임계값 설정을 넣었다(2026-08-25, "UI/UX 완전 똑같이" 요청 - 기존 왼쪽 사이드바에
 * 있던 설정을 여기로 옮김). 저쪽처럼 의미 부류 분류나 LLM 답변생성은 저희 아키텍처에 없어서 그
 * 항목은 넣지 않았다. */
function Card({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div className="bg-[var(--mh-surface)] border border-[var(--mh-border)] rounded-xl p-[18px] shadow-[var(--mh-card-shadow)]">
      <div className="text-[13px] font-extrabold mb-3">{title}</div>
      {children}
      {note && <div className="text-xs text-[var(--mh-muted-2)] mt-2">{note}</div>}
    </div>
  )
}

function Kv({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-[var(--mh-surface-2)] rounded-[10px] px-[15px] py-[13px] text-[13px] text-[#3c3c43] [&>div+div]:mt-[3px]">
      {children}
    </div>
  )
}

interface Props {
  result: PipelineResult
  embOptions: EmbeddingModelOption[]
  embModel: string
  onEmbModelChange: (modelId: string) => void
  similarityThreshold: number
  onSimilarityThresholdChange: (v: number) => void
}

export function AnalysisPanel({
  result, embOptions, embModel, onEmbModelChange, similarityThreshold, onSimilarityThresholdChange,
}: Props) {
  const totalAnswers = result.retrieval_candidates.length
  const withKeyword = result.retrieval_candidates.filter((c) => c.keywords[0]?.keyword).length
  const noKeyword = totalAnswers - withKeyword

  const glosses = result.recommended_glosses
  const exactCount = glosses.filter((g) => g.is_exact).length
  const withEvidenceCount = glosses.filter((g) => !g.is_exact && g.evidence.length > 0).length
  const noEvidenceCount = glosses.length - exactCount - withEvidenceCount

  const t = result.timing
  const timingRows: [string, number][] = [
    ['문진 단계·세부분류 예측', t.classify_ms],
    ['기존 코퍼스 답변 검색', t.retrieve_ms],
    ['대표 키워드 추출', t.keyword_extract_ms],
    ['표제어 매핑', t.gloss_ms],
  ]

  const selectedEmbOption = embOptions.find((o) => o.model_id === embModel)

  return (
    <div className="space-y-[18px]">
      <Card title="1. 질문 분류">
        <Kv>
          <div><span className="text-[var(--mh-muted)]">문진 단계:</span> {result.top_stage.label} ({(result.top_stage.prob * 100).toFixed(1)}%)</div>
          <div><span className="text-[var(--mh-muted)]">세부분류:</span> {result.top_sub.label} ({(result.top_sub.prob * 100).toFixed(1)}%)</div>
          {result.ground_truth && (
            <div className="text-[var(--mh-muted)]">코퍼스 정답: {result.ground_truth.stage} / {result.ground_truth.subcategory}</div>
          )}
        </Kv>
      </Card>

      <Card title="2. 답변 검색">
        <Kv>
          <div><span className="text-[var(--mh-muted)]">출처:</span> 기존 코퍼스 검색(LLM 생성 없음)</div>
          <div><span className="text-[var(--mh-muted)]">유사도:</span> {(result.similarity * 100).toFixed(1)}%</div>
          <div><span className="text-[var(--mh-muted)]">매칭된 기존 질문:</span> {result.matched_question ?? '(없음)'}</div>
          <div><span className="text-[var(--mh-muted)]">답변 풀:</span> {totalAnswers}개</div>
        </Kv>
      </Card>

      <Card
        title={`3. 환자 예상 답변 Pool (${totalAnswers}개)`}
        note="표제어는 이 답변들의 핵심 키워드에서 나옵니다. 답변 자체는 최종 출력이 아닙니다."
      >
        <div className="flex flex-col gap-1.5">
          {result.retrieval_candidates.map((c, i) => {
            const kw = c.keywords[0]
            return (
              <div key={i} className="bg-white border border-[var(--mh-border)] rounded-lg px-2.5 py-2 text-[13px]">
                <div>{c.answer}</div>
                {kw?.keyword ? (
                  <div className="text-xs font-semibold text-[var(--mh-ok)]">핵심 키워드: {kw.keyword}</div>
                ) : (
                  <div className="text-xs font-medium text-[#b00020]">핵심 키워드: 표현 가능한 글로스 없음</div>
                )}
              </div>
            )
          })}
        </div>
      </Card>

      <Card title="4. 키워드 확정">
        <Kv>
          답변 {totalAnswers}개 중 <span className="font-semibold text-[var(--mh-ok)]">{withKeyword}개 키워드 확정</span>
          {noKeyword > 0 && <> · <span className="text-[var(--mh-muted)]">{noKeyword}개는 키워드 없음</span></>}
        </Kv>
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer font-semibold text-[var(--mh-accent)] hover:underline">키워드 선정 기준 보기</summary>
          <div className="mt-2 divide-y divide-[var(--mh-border)] border border-[var(--mh-border)] rounded-lg overflow-hidden">
            {KEYWORD_SELECTION_PRINCIPLES.map((p) => (
              <div key={p.title} className="px-3 py-2.5 bg-[var(--mh-surface)]">
                <div className="text-[13px] font-bold mb-0.5">{p.title}</div>
                <div className="text-[var(--mh-muted)] leading-relaxed">{p.desc}</div>
                <div className="text-[var(--mh-accent)] bg-[var(--mh-surface-2)] rounded px-1.5 py-0.5 mt-1 inline-block">예: {p.example}</div>
              </div>
            ))}
          </div>
          <div className="mt-2 text-[var(--mh-muted-2)] leading-relaxed">
            학습에 안 쓴 데이터로 분리 검증(train/valid/test + 5-fold 교차검증) — 정확도 94.93% ± 0.87%p (fold별 93.77~96.35%).
            검증도 같은 코퍼스 내부라 다른 병원·표현 방식의 새 데이터에도 그대로일지는 별도 확인 필요.
          </div>
        </details>
      </Card>

      <Card
        title={`5. 표제어 집계 (${glosses.length}개, 컷 없이 전체)`}
        note={`근거 인정 기준(유사도 ${result.evidence_min_score.toFixed(2)})은 고정값이 아니라, 정확일치를 뺀 나머지 점수를 정렬해서 상위 15%에 해당하는 점수로 매 질문마다 다시 계산합니다(0.5~0.9 범위로 제한). 이번 질문에서는 상위 15% 지점이 ${result.evidence_min_score.toFixed(2)}이었다는 뜻입니다.`}
      >
        <Kv>
          <div>✅ 정확일치: <span className="font-semibold">{exactCount}개</span></div>
          <div>근거 있음(유사도 {result.evidence_min_score.toFixed(2)} 이상, 상위 15%): <span className="font-semibold">{withEvidenceCount}개</span></div>
          <div className="text-[var(--mh-muted)]">근거 없음(유사도 {result.evidence_min_score.toFixed(2)} 미만, 순위만 표시): {noEvidenceCount}개</div>
        </Kv>
      </Card>

      <Card title={`6. 처리 시간 (모델: ${result.emb_model_used.label})`}>
        <Kv>
          {timingRows.map(([label, ms]) => (
            <div key={label} className="flex justify-between">
              <span className="text-[var(--mh-muted)]">{label}</span>
              <span className="tabular-nums">{ms.toFixed(0)}ms</span>
            </div>
          ))}
          <div className="flex justify-between font-semibold border-t border-[var(--mh-border)] pt-1.5 mt-1.5">
            <span>총 소요 시간</span>
            <span className="tabular-nums">{t.total_ms.toFixed(0)}ms</span>
          </div>
        </Kv>
        {t.cold_start && (
          <div className="mt-2 rounded-[10px] px-[15px] py-[13px] text-[13px] leading-[1.6] bg-[#fff8e1] border border-[#ffe082] text-[#7a5b0b]">
            ⚠ 이번 요청에서 모델을 새로 로드함(콜드스타트) — 시간이 평소보다 길게 잡혔을 수 있음
          </div>
        )}
      </Card>

      <Card title="7. 실행 설정" note="여기서 바꾼 설정은 다음 질문부터 그대로 적용됩니다.">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <label className="text-[11px] text-[var(--mh-muted)] font-bold">임베딩 모델 (검색용)</label>
            <select
              className="w-full bg-white border border-[var(--mh-border)] rounded-lg text-[var(--mh-text)] px-2.5 py-2 text-[13px] outline-none focus:border-[var(--mh-accent)]"
              value={embModel}
              onChange={(e) => onEmbModelChange(e.target.value)}
            >
              {embOptions.map((opt) => (
                <option key={opt.model_id} value={opt.model_id}>
                  {opt.loaded ? '✅' : '⏳'} {opt.label}
                </option>
              ))}
            </select>
            {selectedEmbOption && (
              <span className={'text-xs font-semibold ' + (selectedEmbOption.loaded ? 'text-[var(--mh-ok)]' : 'text-amber-700')}>
                {selectedEmbOption.loaded ? '✅ 이미 로드됨' : '⏳ 처음 검색 시 로딩 시간 걸림'}
              </span>
            )}
          </div>
          <div className="flex flex-col gap-1.5 col-span-2">
            <label className="text-[11px] text-[var(--mh-muted)] font-bold">검색(retriever) 유사도 임계값: {similarityThreshold.toFixed(2)}</label>
            <input
              type="range" min={0} max={1} step={0.01}
              value={similarityThreshold}
              onChange={(e) => onSimilarityThresholdChange(Number(e.target.value))}
              className="w-full"
            />
          </div>
        </div>
      </Card>
    </div>
  )
}
