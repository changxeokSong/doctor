import type { CandidateKeyword, EmbeddingModelOption, GlossTableRow, PipelineResult } from '../api/types'
import { EmbModelSelect } from './EmbModelSelect'
import { RecommendationStats, RecommendedGlossesTable } from './CandidatesPanel'
import { stripCategory } from '../utils/gloss'

const KEYWORD_SELECTION_PRINCIPLES = [
  { title: '핵심 원칙', desc: '답변 문장 안 실제 단어·구를 그대로 선택', example: '앉아 있으면 더 아픕니다. → 앉아 있으면' },
  { title: '일반 서술어 지양', desc: "'아픕니다/있습니다' 단독 선택 지양 — 자세·부위·강도·상태·동작 우선", example: '걸으면 더 아파요. → 걸으면' },
  { title: '동사 포함 가능', desc: '힘 빠짐·저림·부음 등 필요시 동사/상태어 선택', example: '가끔 힘이 빠집니다. → 빠집니다' },
  { title: '예/아니오 문항', desc: '실제 답변의 판단어·구체 상태어 선택', example: '아니요, 저림은 없어요. → 없어요' },
]

const pct = (v: number) => `${(v * 100).toFixed(1)}%`
const ms = (v: number) => `${v.toFixed(0)}ms`

function Card({ title, note, children }: { title: string; note?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="card">
      <div className="card-title">{title}</div>
      {children}
      {note && <div className="card-note">{note}</div>}
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="evidence-row">
      <div className="evidence-gloss">{label}</div>
      <div className="evidence-sents"><div className="evidence-sent">{children}</div></div>
    </div>
  )
}

/** 키워드가 도달한 표제어를 "이름_인덱스"로 - 정확일치가 없으면 1순위 후보를 유사도와 함께 보여준다. */
function KeywordMapping({ kw }: { kw: CandidateKeyword | undefined }) {
  if (!kw?.keyword) return <div className="pool-core missing">핵심 키워드: 표현 가능한 글로스 없음</div>
  const hit = kw.gloss_exact ?? kw.gloss_top
  if (!hit || kw.no_gloss) {
    return <div className="pool-core missing">핵심 키워드: {kw.keyword} → 표현 가능한 글로스 없음</div>
  }
  return (
    <div className="pool-core">
      핵심 키워드: {kw.keyword} → {hit.name}_{hit.origin_number}
      {!kw.gloss_exact && <span className="pool-meta"> (정확일치 아님 · 유사도 {hit.score.toFixed(3)})</span>}
    </div>
  )
}

const PRIORITY_REASON: Record<'gloss' | 'category', string> = {
  gloss: '표제어 우선',
  category: '카테고리 우선',
}

const tierOf = (r: GlossTableRow) => (r.priorityKind === 'gloss' ? 0 : r.priorityKind === 'category' ? 1 : 2)

/** 정렬 방식을 문구로 하드코딩하지 않고 응답 순서에서 역으로 판별한다 - 백엔드 정렬키가 바뀌어도
 * 화면 설명이 실제와 어긋나지 않는다. */
function describeOrder(rows: GlossTableRow[]) {
  // 정확일치는 묶음과 무관하게 맨 앞으로 빠지므로 묶음 판별에서 제외한다.
  let lead = 0
  while (lead < rows.length && rows[lead].score >= 0.9999) lead++
  const rest = rows.slice(lead)
  const tiers = rest.map(tierOf)
  const grouped = tiers.every((t, i) => i === 0 || t >= tiers[i - 1])
  const withinScoreDesc = rest.every(
    (r, i) => i === 0 || tierOf(r) !== tierOf(rest[i - 1]) || rest[i - 1].score >= r.score - 1e-9,
  )
  if (!grouped || !withinScoreDesc) return '정확일치 > 점수 구간 > 표제어 우선 > 카테고리 우선 > 점수 순으로 봅니다.'
  return `${lead > 0 ? `정확일치 ${lead}개를 맨 앞에 두고, 그다음 ` : ''}표제어 우선 → 카테고리 우선 → 나머지 순으로 묶고, 각 묶음 안에서는 점수 내림차순으로 정렬합니다.`
}

/** 최종 순서(백엔드 정렬)와 순수 유사도 순서를 대조해 어떤 표제어가 몇 칸 움직였는지 계산한다.
 * table_rows는 이미 최종 순서로 와서 인덱스가 곧 최종 순위 - 유사도 순위만 여기서 매긴다. */
function rankMoves(rows: GlossTableRow[]) {
  const scoreRank = new Map<number, number>()
  rows
    .map((row, i) => ({ row, i }))
    .sort((a, b) => b.row.score - a.row.score || a.i - b.i)
    .forEach(({ row }, i) => scoreRank.set(row.glossId, i + 1))
  return rows.map((row, i) => ({
    row, finalRank: i + 1, scoreRank: scoreRank.get(row.glossId)!, delta: scoreRank.get(row.glossId)! - (i + 1),
  }))
}

function RankReassignment({ rows }: { rows: GlossTableRow[] }) {
  const moves = rankMoves(rows)
  const movedUp = moves.filter((m) => m.delta > 0)
  const byGloss = movedUp.filter((m) => m.row.priorityKind === 'gloss').length
  const byCategory = movedUp.filter((m) => m.row.priorityKind === 'category').length
  // 우선순위 태그가 없는데도 올라간 행 - 위 행들이 앞당겨지면서 상대적으로 밀려 올라온 것.
  const byPush = movedUp.length - byGloss - byCategory
  const top = [...moves].filter((m) => m.delta !== 0).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 12)

  if (movedUp.length === 0) return <Row label="순위 재배정">유사도 순서 그대로입니다 — 앞당겨진 표제어가 없습니다.</Row>

  return (
    <>
      <Row label="정렬 방식">{describeOrder(rows)}</Row>
      <Row label="순위 재배정">
        점수 순위보다 위로 올라온 표제어 {movedUp.length}개 (표제어 우선 {byGloss} · 카테고리 우선 {byCategory}
        {byPush > 0 && ` · 밀림으로 인한 상승 ${byPush}`}) ·
        묶음 크기 표제어 우선 {rows.filter((r) => tierOf(r) === 0).length} / 카테고리 우선{' '}
        {rows.filter((r) => tierOf(r) === 1).length} / 나머지 {rows.filter((r) => tierOf(r) === 2).length}
      </Row>
      <details style={{ marginTop: 12, fontSize: 12 }}>
        <summary className="app-link" style={{ cursor: 'pointer' }}>
          점수 순위와 최종 순위가 다른 표제어 보기 ({top.length}/{moves.filter((m) => m.delta !== 0).length}개)
        </summary>
        <div className="table-scroll" style={{ marginTop: 8, maxHeight: 300 }}>
          <table className="table rank-table">
            <thead><tr><th>표제어</th><th>점수</th><th>점수 순위</th><th>최종 순위</th><th>이동</th><th>사유</th></tr></thead>
            <tbody>
              {top.map((m) => (
                <tr key={m.row.glossId}>
                  <td className="gl">{m.row.keyword.split(',')[0]}</td>
                  <td>{m.row.score.toFixed(2)}</td>
                  <td>{m.scoreRank}</td>
                  <td>{m.finalRank}</td>
                  <td style={{ color: m.delta > 0 ? '#0a7d32' : '#b00020', fontWeight: 700 }}>
                    {m.delta > 0 ? `▲${m.delta}` : `▼${-m.delta}`}
                  </td>
                  <td>{m.row.priorityKind ? PRIORITY_REASON[m.row.priorityKind] : '위 행이 앞당겨져 밀림'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card-note">
          우선순위는 세부분류별로 미리 지정된 표제어·분류 목록입니다 — 점수가 조금 낮아도 이 문진 세부분류에서
          실제로 쓸 표제어를 위로 올립니다. 점수 순서로만 보려면 "글로스·문진 현황" 화면에서 스코어 헤더를 누르세요.
        </div>
      </details>
    </>
  )
}

interface Props {
  result: PipelineResult
  embOptions: EmbeddingModelOption[]
  embModel: string
  onEmbModelChange: (modelId: string) => void
  similarityThreshold: number
  onSimilarityThresholdChange: (v: number) => void
  onRerun: (question: string) => void
  rerunning: boolean
}

export function AnalysisPanel({
  result, embOptions, embModel, onEmbModelChange,
  similarityThreshold, onSimilarityThresholdChange, onRerun, rerunning,
}: Props) {
  const { classification: cls, retrieval: rt, answerPool: pool, cutoff, latency } = result.analysis
  const classMismatch = cls.predictedStage !== cls.usedStage || cls.predictedSub !== cls.usedSub

  const latencyRows: [string, number][] = [
    ['문진 단계·세부분류 예측', latency.classifyMs],
    ['기존 코퍼스 답변 검색', latency.retrieveMs],
    ['대표 키워드 추출', latency.keywordExtractMs],
    ['표제어 점수 계산·정렬', latency.glossScoringMs],
  ]
  const selectedEmbOption = embOptions.find((o) => o.model_id === embModel)

  return (
    <>
      <Card title="1. 질문 분류">
        <div className="kv">
          <div><strong>의사 질문:</strong> {cls.question}</div>
          <div>
            <strong>모델 예측:</strong> {cls.predictedStage} ({pct(cls.predictedStageProb)}) / {cls.predictedSub} ({pct(cls.predictedSubProb)})
            <span className="pool-meta"> · 2위와의 격차 {cls.subMargin.toFixed(2)}</span>
          </div>
          <div>
            <strong>실제 사용:</strong> {cls.usedStage} / {cls.usedSub}
            {classMismatch && <span className="pool-meta"> · 매칭된 기존 질문의 분류를 따랐습니다</span>}
          </div>
          {result.ground_truth && (
            <div><strong>코퍼스 정답:</strong> {result.ground_truth.stage} / {result.ground_truth.subcategory}</div>
          )}
          <div><strong>판단 근거:</strong> {cls.reason}</div>
          <div><strong>검색 대상 세부분류:</strong> {cls.searchedSubs.join(' · ')}</div>
          <div><strong>경로:</strong> {cls.path} · {ms(cls.latencyMs)}</div>
        </div>
        <div className="ask-row">
          <button type="button" className="btn ghost small" disabled={rerunning} onClick={() => onRerun(cls.question)}>
            이 질문 다시 실행
          </button>
          <span className="hint">아래 6번 실행 설정이 그대로 적용됩니다</span>
        </div>
      </Card>

      <Card
        title="2. 추천 통계"
        note="추천 표제어는 전부 답변 원문 근거에서 나옵니다 — 질문 의도로 표제어를 늘리거나 의미 부류를 붙이는 단계가 없어 해당 통계도 두지 않습니다."
      >
        <RecommendationStats stats={result.stats} showTitle={false} />
      </Card>

      <Card title="3. 표제어를 만든 경로">
        <Row label="답변 pool 출처">
          {pool.sources.length === 0
            ? '없음'
            : pool.sources.map((s) => `${s.source} ${s.count}개`).join(' · ')}
        </Row>
        <Row label="질문 검색 방식">
          {rt.usedFilter
            ? `세부분류 상위 3개로 후보 축소 (${rt.candidateCount}/${rt.corpusCount}건 비교)`
            : `후보 부족으로 필터 해제, 코퍼스 전체 ${rt.corpusCount}건 비교`}
        </Row>
        <Row label="최고 유사도">
          {pct(rt.similarity)} / 임계값 {pct(rt.similarityThreshold)} — {rt.retrievalOk ? '통과' : '미달'}
          {rt.matchedQuestion && <span className="pool-meta"> · "{rt.matchedQuestion}" ({rt.matchedQuestionSource})</span>}
        </Row>
        <Row label="키워드 확정">
          답변 {pool.total}개 중 {pool.keywordFound}개 확정
          {pool.noGlossCount > 0 && ` · ${pool.noGlossCount}개는 표현 가능한 글로스 없음`}
          {` · 표제어 산출에 실제로 기여한 답변 ${pool.resolved}개`}
        </Row>
        <Row label="표제어 구성">
          답변 키워드와 사전 표제어를 임베딩 유사도로 비교해 표제어별 최고점으로 집계하고,
          정확일치이거나 근거 문턱 이상인 것만 남깁니다.
        </Row>
        <Row label="컷오프">
          점수 {cutoff.minScore} 이상 (후보 상위 {pct(cutoff.topPercentile)} 지점에서 동적 결정) · 제외 {cutoff.excludedCount}개
        </Row>
        <Row label="점수 보정">
          표의 "점수"는 순수 임베딩 유사도가 아닙니다 — 이 세부분류의 우선 카테고리에 속하는 표제어는 컷오프에서
          아깝게 탈락하지 않도록 소폭 가산된 값입니다(정확일치는 가산 없음). 순위 비교도 이 보정 점수 기준입니다.
        </Row>
        <RankReassignment rows={result.table_rows} />

        {cutoff.excludedSample.length > 0 && (
          <details style={{ marginTop: 12, fontSize: 12 }}>
            <summary className="app-link" style={{ cursor: 'pointer' }}>
              컷오프로 제외된 표제어 보기 ({cutoff.excludedSample.length}/{cutoff.excludedCount}개)
            </summary>
            <div className="table-scroll" style={{ marginTop: 8, maxHeight: 300 }}>
              <table className="table compact-table">
                <thead><tr><th>#</th><th>표제어</th><th>인덱스</th><th>점수</th><th>분류</th></tr></thead>
                <tbody>
                  {cutoff.excludedSample.map((g, i) => (
                    <tr key={g.glossId}>
                      <td className="row-number">{i + 1}</td>
                      <td className="gl">{g.keyword}</td>
                      <td>{g.glossId}</td>
                      <td>{g.score.toFixed(2)}</td>
                      <td>{stripCategory(g.category)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card-note">제외 목록은 전체 {cutoff.excludedCount}개 중 상위 일부 표본입니다.</div>
          </details>
        )}

        <div className="result-section-title table-title">단계별 소요 시간</div>
        <div className="stat-chart">
          {latencyRows.map(([label, v]) => (
            <div key={label} className="stat-bar-row">
              <span>{label}</span>
              <div className="stat-bar-track">
                <i className="bar-evidence" style={{ width: `${Math.min(100, (v / Math.max(latency.totalMs, 1)) * 100)}%` }} />
              </div>
              <strong>{ms(v)}</strong>
            </div>
          ))}
          <div className="stat-bar-row">
            <span>총 소요 시간</span>
            <div className="stat-bar-track"><i className="bar-dropped" style={{ width: '100%' }} /></div>
            <strong>{ms(latency.totalMs)}</strong>
          </div>
        </div>
        {result.timing.cold_start && (
          <div className="notice warn" style={{ marginTop: 10 }}>
            ⚠ 이번 요청에서 모델을 새로 로드함(콜드스타트) — 시간이 평소보다 길게 잡혔을 수 있음
          </div>
        )}
      </Card>

      <Card
        title={`4. 환자 예상 답변 Pool (${pool.total}개)`}
        note="표제어는 이 답변들의 핵심 키워드에서 나옵니다. 답변 자체는 최종 출력이 아닙니다."
      >
        <div className="pool-list">
          {result.retrieval_candidates.map((c, i) => (
            <div key={i} className="pool-item">
              <div>{c.answer}</div>
              <KeywordMapping kw={c.keywords[0]} />
              <div className="pool-meta">출처: {c.answer_source}</div>
            </div>
          ))}
        </div>
        <details style={{ marginTop: 10, fontSize: 12 }}>
          <summary className="app-link" style={{ cursor: 'pointer' }}>키워드 선정 기준 보기</summary>
          <div style={{ marginTop: 8, border: '1px solid #e5e5ea', borderRadius: 8, overflow: 'hidden' }}>
            {KEYWORD_SELECTION_PRINCIPLES.map((p, i) => (
              <div key={p.title} style={{ padding: '10px 12px', borderTop: i ? '1px solid #e5e5ea' : 'none' }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 2 }}>{p.title}</div>
                <div style={{ color: '#636366' }}>{p.desc}</div>
                <div style={{ color: '#636af5', background: '#f5f5f7', borderRadius: 4, padding: '2px 6px', marginTop: 4, display: 'inline-block' }}>예: {p.example}</div>
              </div>
            ))}
          </div>
          <div className="card-note">
            학습에 안 쓴 데이터로 분리 검증(train/valid/test + 5-fold 교차검증) — 정확도 94.93% ± 0.87%p (fold별 93.77~96.35%).
            검증도 같은 코퍼스 내부라 다른 병원·표현 방식의 새 데이터에도 그대로일지는 별도 확인 필요.
          </div>
        </details>
      </Card>

      <Card
        title={`5. 핵심 표제어 (${result.table_rows.length}개)`}
        note="전부 답변 원문에서 실제로 뽑아낸 키워드로 도달한 표제어입니다 — 근거 문장의 강조 구간이 그 위치입니다."
      >
        <RecommendedGlossesTable rows={result.table_rows} matchedQuestion={null} showTitle={false} />
      </Card>

      <Card title="6. 실행 설정" note="여기서 바꾼 설정은 다음 질문부터 그대로 적용됩니다.">
        <div className="field-grid">
          <div className="field">
            <label htmlFor="analysis-emb-model-select">임베딩 모델 (검색용)</label>
            <EmbModelSelect id="analysis-emb-model-select" embOptions={embOptions} embModel={embModel} onEmbModelChange={onEmbModelChange} />
            {selectedEmbOption && (
              <span style={{ fontSize: 12, fontWeight: 600, color: selectedEmbOption.loaded ? '#1a7f37' : '#7a5b0b' }}>
                {selectedEmbOption.loaded ? '✅ 이미 로드됨' : '⏳ 처음 검색 시 로딩 시간 걸림'}
              </span>
            )}
          </div>
          <div className="field">
            <label>이번 결과에 쓰인 모델</label>
            <span style={{ fontSize: 13 }}>{result.emb_model_used.label}</span>
          </div>
          <div className="field full">
            <label>검색(retriever) 유사도 임계값: {similarityThreshold.toFixed(2)}</label>
            <input
              type="range" min={0} max={1} step={0.01}
              value={similarityThreshold}
              onChange={(e) => onSimilarityThresholdChange(Number(e.target.value))}
            />
          </div>
        </div>
      </Card>
    </>
  )
}
