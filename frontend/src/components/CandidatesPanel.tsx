import type { GlossTableRow, PipelineStats } from '../api/types'
import { stripCategory } from '../utils/gloss'

/** 163.239.25.74:8777(LLM 기반 시스템)의 "추천 통계" 패널과 같은 마크업(.stat-grid/.stat-chart).
 * "의도 확장"은 백엔드가 아예 내려주지 않는(항상 0인) 값이라 통계에서도 뺐다 - intentRole(질문
 * 대상/보조 부류)과 마찬가지로 우리 아키텍처가 실제로 하지 않는 일을 통계로 보여주면 오해를 준다. */
export function RecommendationStats({ stats, showTitle = true }: { stats: PipelineStats; showTitle?: boolean }) {
  const max = Math.max(stats.final_count, stats.dropped_count, 1)
  const bar = (value: number) => `${Math.max(0, Math.min(100, (value / max) * 100))}%`
  return (
    <>
      {showTitle && <div className="result-section-title">추천 통계</div>}
      <div className="stat-grid stat-grid-5">
        <div className="stat-card"><span>최종 표제어</span><strong>{stats.final_count}</strong><small>개</small></div>
        <div className="stat-card"><span>답변 근거</span><strong>{stats.evidence_count}</strong><small>개</small></div>
        <div className="stat-card"><span>필터 제외</span><strong>{stats.dropped_count}</strong><small>개</small></div>
        <div className="stat-card"><span>답변 매핑</span><strong>{stats.answers_resolved}</strong><small>/{stats.answers_total}</small></div>
        <div className="stat-card"><span>전체 응답시간</span><strong>{(stats.total_ms / 1000).toFixed(2)}s</strong></div>
      </div>
      <div className="stat-chart" aria-label="표제어 구성 통계">
        <div className="stat-bar-row">
          <span>답변 근거</span>
          <div className="stat-bar-track"><i className="bar-evidence" style={{ width: bar(stats.evidence_count) }} /></div>
          <strong>{stats.evidence_count}</strong>
        </div>
        <div className="stat-bar-row">
          <span>필터 제외</span>
          <div className="stat-bar-track"><i className="bar-dropped" style={{ width: bar(stats.dropped_count) }} /></div>
          <strong>{stats.dropped_count}</strong>
        </div>
      </div>
    </>
  )
}

/** 163.239.25.74:8777의 "사용 및 도출 JSON" 뷰어와 같은 마크업(.json-grid/.json-panel). */
export function ResultJsonViewer({ requestBody, resultBody }: { requestBody: unknown; resultBody: unknown }) {
  return (
    <>
      <div className="result-section-title json-title">사용 및 도출 JSON</div>
      <div className="json-grid">
        <details className="json-panel">
          <summary>사용된 요청 JSON</summary>
          <pre>{JSON.stringify(requestBody, null, 2)}</pre>
        </details>
        <details className="json-panel" open>
          <summary>도출된 결과 JSON</summary>
          <pre>{JSON.stringify(resultBody, null, 2)}</pre>
        </details>
      </div>
    </>
  )
}

/** 163.239.25.74:8777의 highlightKeywords()와 같은 효과 — 근거 문장 안에서 실제로 이 표제어를
 * 뽑아낸 구간을 <mark>로 표시한다. 저쪽은 문자열 재검색(첫 일치)으로 찾지만, 우리는 백엔드
 * SpanTagger가 실제로 태깅한 위치(start/end)를 그대로 쓸 수 있어 더 정확하다. */
function HighlightedSentence({ sentence, start, end }: { sentence: string; start: number | null; end: number | null }) {
  if (start == null || end == null) return <>{sentence}</>
  return (
    <>
      {sentence.slice(0, start)}
      <mark>{sentence.slice(start, end)}</mark>
      {sentence.slice(end)}
    </>
  )
}

const SOURCE_LABEL: Record<GlossTableRow['source'], string> = {
  answer_evidence: '답변 근거',
  intent_expansion: '의도 확장',
}
const SOURCE_BADGE_CLASS: Record<GlossTableRow['source'], string> = {
  answer_evidence: 'source-badge evidence-source',
  intent_expansion: 'source-badge expanded-source',
}

interface RecommendedGlossesTableProps {
  rows: GlossTableRow[]
  matchedQuestion: string | null
  showTitle?: boolean
}

/** 163.239.25.74:8777의 키워드 결과 표(.table.keyword-table)와 같은 컬럼 구성(#/표제어/인덱스/
 * 분류/출처/근거 문장). "의미 부류" 컬럼(intentRole/intentLabel)은 LLM이 질문 의도를 해석해
 * 붙이는 개념이라 우리 아키텍처로는 원칙 있게 재현할 방법이 없어 뺐다 — 나머지는 우리 데이터로
 * 그대로 채울 수 있다. */
export function RecommendedGlossesTable({ rows, matchedQuestion, showTitle = true }: RecommendedGlossesTableProps) {
  if (rows.length === 0) {
    return <div className="empty-note">추천할 표제어가 없습니다.</div>
  }

  return (
    <>
      {matchedQuestion && (
        <div className="latest-question">
          "{matchedQuestion}" 질문에 대한 답변들에서 키워드를 뽑고, 그 키워드로 아래 표제어를 추천했습니다.
        </div>
      )}
      {showTitle && <div className="result-section-title table-title">키워드 목록</div>}
      <div className="table-scroll keyword-table-scroll">
        <table className="table keyword-table">
          <thead>
            <tr>
              <th>#</th>
              <th>표제어</th>
              <th>인덱스</th>
              <th>분류</th>
              <th>출처</th>
              <th>근거 문장</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const [first, ...rest] = r.keyword.split(',')
              return (
                <tr key={r.glossId}>
                  <td className="row-number">{i + 1}</td>
                  <td className="gl">
                    <strong>{first}</strong>
                    {rest.length > 0 && <small>{rest.join(', ')}</small>}
                  </td>
                  <td>{r.glossId}</td>
                  <td>{stripCategory(r.category)}</td>
                  <td><span className={SOURCE_BADGE_CLASS[r.source]}>{SOURCE_LABEL[r.source]}</span></td>
                  <td><HighlightedSentence sentence={r.evidenceSentence} start={r.evidenceStart} end={r.evidenceEnd} /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}
