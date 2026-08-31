import { useState } from 'react'
import type { RecommendedGloss } from '../api/types'

interface HighlightProps {
  answer: string
  keyword: string
  start?: number | null
  end?: number | null
}

function HighlightedEvidenceSentence({ answer, keyword, start, end }: HighlightProps) {
  const valid = start != null && end != null && answer.slice(start, end) === keyword  // 백엔드 태깅 위치 우선, indexOf는 폴백
  const idx = valid ? start : answer.indexOf(keyword)
  if (idx === -1) return <>{answer}</>
  const idxEnd = valid ? end : idx + keyword.length
  return (
    <>
      {answer.slice(0, idx)}
      <mark className="bg-[#fff3bf] text-inherit rounded-[3px] px-0.5 font-semibold">
        {answer.slice(idx, idxEnd)}
      </mark>
      {answer.slice(idxEnd)}
    </>
  )
}

/** 접힌 "전체 654개 순위" 표 안에서 쓰는 축약형 근거 - 문장 하나만 보여주고 나머지는 "더보기". */
function TableEvidenceCell({ evidence, answers, evidenceMinScore }: { evidence: RecommendedGloss['evidence']; answers: string[]; evidenceMinScore: number }) {
  const [expanded, setExpanded] = useState(false)
  if (evidence.length === 0) {
    return (
      <div className="mt-0.5 text-xs text-[var(--mh-muted-2)]">
        뚜렷한 근거 답변 없음 (유사도 {evidenceMinScore.toFixed(2)} 미만)
      </div>
    )
  }
  const shown = expanded ? evidence : evidence.slice(0, 1)
  return (
    <div className="mt-0.5 space-y-0.5">
      {shown.map((e, j) => (
        <div key={j} className="text-xs leading-snug">
          <HighlightedEvidenceSentence answer={answers[e.answer_index] ?? ''} keyword={e.keyword} start={e.start} end={e.end} />
        </div>
      ))}
      {evidence.length > 1 && (
        <button
          type="button"
          className="text-xs text-[var(--mh-accent)] font-semibold hover:underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? '접기 ▲' : `더보기 (+${evidence.length - 1}) ▼`}
        </button>
      )}
    </div>
  )
}

/** evidence는 백엔드에서 이미 점수 내림차순 정렬돼 오므로 evidence[0]가 최선의 근거다. */
function EvidenceRow({ name, evidence, answers }: { name: string; evidence: RecommendedGloss['evidence']; answers: string[] }) {
  if (evidence.length === 0) return null
  const best = evidence[0]
  return (
    <div className="grid grid-cols-[minmax(96px,168px)_1fr] gap-3 py-[7px] border-b border-[#f7f7fa] last:border-b-0 items-baseline">
      <span className="text-[13px] font-bold text-[var(--mh-ok)] break-all">{name}</span>
      <span className="text-[13px] text-[#3c3c43]">
        <HighlightedEvidenceSentence answer={answers[best.answer_index] ?? ''} keyword={best.keyword} start={best.start} end={best.end} />
      </span>
    </div>
  )
}

/** 3단계: 정확일치(진한 초록) / 임계값~1.0 중간점 이상(중간 초록) / 중간점 미만(연한 초록).
 * 임계값 미달은 core 필터에서 이미 빠지므로 여기 안 들어온다. */
function pillTier(g: RecommendedGloss, evidenceMinScore: number): 1 | 2 | 3 {
  if (g.is_exact) return 1
  const midpoint = evidenceMinScore + (1 - evidenceMinScore) / 2
  return g.score >= midpoint ? 2 : 3
}

function pillClass(tier: 1 | 2 | 3): string {
  if (tier === 1) return 'bg-[#1a7f37] text-white'
  if (tier === 2) return 'bg-[#6fcf8f] text-[#0a3d1f]'
  return 'bg-[#e3f5e8] text-[#14612b] border border-[#b7ebc6]'
}

/** "의미 부류" 칼럼은 우리 아키텍처에 없는 개념이라 예측 세부분류(subLabel)로 대신 채운다. */
export function GlossDetailTable({ glosses, subLabel, answers }: { glosses: RecommendedGloss[]; subLabel: string; answers: string[] }) {
  const core = glosses.filter((g) => g.is_exact || g.evidence.length > 0)
  return (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-[var(--mh-muted-2)] uppercase tracking-wide">
            <th className="text-left font-bold px-2 py-2">표제어</th>
            <th className="w-16 text-right font-bold px-2 py-2 whitespace-nowrap">인덱스</th>
            <th className="w-16 text-right font-bold px-2 py-2 whitespace-nowrap">스코어</th>
            <th className="w-28 text-left font-bold px-2 py-2 whitespace-nowrap">세부분류</th>
            <th className="text-left font-bold px-2 py-2">근거 키워드와 문장</th>
          </tr>
        </thead>
        <tbody>
          {core.map((g) => {
            const best = g.evidence[0]
            return (
              <tr key={g.origin_number} className={'border-t border-[var(--mh-border)] align-top ' + (g.is_exact ? 'bg-[var(--mh-ok-soft)]' : '')}>
                <td className="px-2 py-2.5 font-bold text-[var(--mh-ok)] break-all">{g.name}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-xs text-[var(--mh-muted-2)] whitespace-nowrap">{g.origin_number}</td>
                <td className="px-2 py-2.5 text-right tabular-nums font-semibold whitespace-nowrap">
                  {g.is_exact ? <span className="text-[var(--mh-ok)]">정확</span> : g.score.toFixed(2)}
                </td>
                <td className="px-2 py-2.5 text-xs text-[var(--mh-muted)] whitespace-nowrap">{subLabel}</td>
                <td className="px-2 py-2.5 text-[13px] text-[#3c3c43]">
                  {best ? (
                    <>
                      <div className="text-xs text-[var(--mh-muted-2)] font-semibold">근거 키워드 · {best.keyword}</div>
                      <div><HighlightedEvidenceSentence answer={answers[best.answer_index] ?? ''} keyword={best.keyword} start={best.start} end={best.end} /></div>
                    </>
                  ) : (
                    <span className="text-xs text-[var(--mh-muted-2)]">직접 근거 문장 없음</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

interface RecommendedGlossesTableProps {
  glosses: RecommendedGloss[]
  matchedQuestion: string | null
  answers: string[]
  stageLabel: string
  subLabel: string
  evidenceMinScore: number
}

export function RecommendedGlossesTable({ glosses, matchedQuestion, answers, stageLabel, subLabel, evidenceMinScore }: RecommendedGlossesTableProps) {
  // 중간값 이상 표제어가 MIN_VISIBLE보다 적으면 core(점수순)에서 채워 최소 개수를 보장한다.
  const MIN_VISIBLE = 10
  const [showBelowMidpoint, setShowBelowMidpoint] = useState(false)
  if (glosses.length === 0) {
    return (
      <div className="text-xs text-[var(--mh-muted-2)] border border-[var(--mh-border)] rounded-xl p-3 mb-3">
        추천 표제어가 없습니다.
      </div>
    )
  }
  const core = glosses.filter((g) => g.is_exact || g.evidence.length > 0)
  // core는 순수 점수순이 아니라 세부분류 우선순위가 섞인 정렬이라(services.py), 앞에서부터 N개를
  // 자르면 tier 1/2 항목이 뒤로 밀려 접힐 수 있다 - tier로 직접 걸러서 절대 안 숨게 한다.
  const tier12 = core.filter((g) => pillTier(g, evidenceMinScore) !== 3)
  const tier3 = core.filter((g) => pillTier(g, evidenceMinScore) === 3)
  const primary = tier12.length >= MIN_VISIBLE
    ? tier12
    : [...tier12, ...tier3.slice(0, MIN_VISIBLE - tier12.length)]
  const primarySet = new Set(primary.map((g) => g.origin_number))
  const secondary = core.filter((g) => !primarySet.has(g.origin_number))
  const visibleCore = showBelowMidpoint ? core : primary
  return (
    <div className="bg-[var(--mh-surface)] border border-[var(--mh-border)] rounded-xl mb-3 overflow-hidden shadow-[var(--mh-card-shadow)]">
      <div className="flex items-baseline justify-between gap-3 flex-wrap px-[18px] pt-[18px]">
        <span className="text-[13px] font-extrabold">핵심 표제어 {core.length}개</span>
        <span className="text-xs text-[var(--mh-muted-2)]">{stageLabel} · {subLabel}</span>
      </div>
      {matchedQuestion && (
        <div className="px-[18px] pt-2 text-xs text-[var(--mh-muted)] leading-relaxed">
          <div className="font-semibold">"{matchedQuestion}"</div>
          <div>질문에 대한 답변들에서 키워드를 뽑고,</div>
          <div>그 키워드로 아래 표제어를 추천했습니다.</div>
          <div className="mt-1 text-[var(--mh-muted-2)]">
            <div>정확일치이거나, 나머지 중 유사도 상위 15%에 든 표제어만 아래 색깔 표시에 나옵니다.</div>
            <div>이번 질문의 점수 분포로 매번 다시 계산됨 — 자세한 기준은 "분석 보기"에서 확인.</div>
          </div>
        </div>
      )}
      <div className="px-[18px] pt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--mh-muted)]">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-[#1a7f37] inline-block" /> 정확일치
        </span>
        <span
          className="inline-flex items-center gap-1.5 cursor-help"
          title="임계값과 1.0 사이 중간값 - 이 값 이상이면 특히 강한 근거로 봅니다"
        >
          <span className="w-3 h-3 rounded-full bg-[#6fcf8f] inline-block" /> 유사도 {((evidenceMinScore + (1 - evidenceMinScore) / 2)).toFixed(2)} 이상
        </span>
        {secondary.length > 0 && (
          <span
            className="inline-flex items-center gap-1.5 cursor-help"
            title="중간값 미만(근거는 있지만 상대적으로 약함) - 기본은 접혀 있고 아래 '더보기'로 펼칩니다"
          >
            <span className="w-3 h-3 rounded-full bg-[#e3f5e8] border border-[#b7ebc6] inline-block" /> 유사도 {evidenceMinScore.toFixed(2)} 이상 (중간값 미만)
          </span>
        )}
      </div>
      <div className="p-[18px] flex flex-wrap gap-[9px]">
        {visibleCore.map((g) => {
          const [first, ...rest] = g.name.split(',')
          return (
            <span
              key={g.origin_number}
              className={'inline-flex items-baseline gap-1.5 rounded-[22px] px-4 py-2 max-w-full border border-transparent leading-[1.35] ' + pillClass(pillTier(g, evidenceMinScore))}
            >
              <b className="text-base font-bold">{first}</b>
              {rest.length > 0 && <span className="text-xs opacity-70 break-all">{rest.join(', ')}</span>}
              <span className="text-[11px] opacity-60 tabular-nums">{g.origin_number}</span>
            </span>
          )
        })}
        {secondary.length > 0 && (
          <button
            type="button"
            className="inline-flex items-baseline gap-1.5 rounded-[22px] px-4 py-2 leading-[1.35] text-[13px] font-semibold text-[var(--mh-accent)] border border-[var(--mh-border)] hover:bg-[var(--mh-surface-2)]"
            onClick={() => setShowBelowMidpoint((v) => !v)}
          >
            {showBelowMidpoint ? '접기 ▲' : `더보기 (+${secondary.length}) ▼`}
          </button>
        )}
      </div>
      <div className="px-[18px] pb-[18px] mt-1 border-t border-[var(--mh-border)] pt-3.5">
        <div className="text-xs font-bold text-[var(--mh-muted-2)] mb-2.5">
          근거 문장 · {visibleCore.length}개 표제어가 아래 답변에서 나왔습니다
          {secondary.length > 0 && !showBelowMidpoint && (
            <span className="font-normal text-[var(--mh-muted-2)]"> (중간값 미만 {secondary.length}개는 위 '더보기'로 펼쳐야 보입니다)</span>
          )}
        </div>
        <div>
          {visibleCore.map((g) => (
            <EvidenceRow key={g.origin_number} name={g.name} evidence={g.evidence} answers={answers} />
          ))}
        </div>
      </div>
      <details className="border-t border-[var(--mh-border)]">
        <summary className="cursor-pointer text-xs font-bold px-4 py-2.5 text-[var(--mh-muted)]">
          전체 {glosses.length}개 순위 보기 (스코어순, 컷 없음)
        </summary>
        <div className="overflow-auto max-h-[calc(100vh-9rem)]">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-[var(--mh-surface)]">
              <tr className="text-xs text-[var(--mh-muted-2)] uppercase tracking-wide">
                <th className="w-10 text-right font-bold px-2 py-2 whitespace-nowrap">순위</th>
                <th className="w-14 text-right font-bold px-2 py-2 whitespace-nowrap">인덱스</th>
                <th className="text-left font-bold px-2 py-2">표제어</th>
                <th className="w-16 text-right font-bold px-2 py-2 whitespace-nowrap">스코어</th>
              </tr>
            </thead>
            <tbody>
              {glosses.map((g, i) => (
                <tr
                  key={g.origin_number}
                  className={'border-t border-[var(--mh-border)] ' + (g.is_exact ? 'bg-[var(--mh-ok-soft)]' : '')}
                >
                  <td className="w-10 text-right px-2 py-2 tabular-nums text-[var(--mh-muted)] whitespace-nowrap">{i + 1}</td>
                  <td className="w-14 text-right px-2 py-2 tabular-nums text-xs text-[var(--mh-muted-2)] whitespace-nowrap">{g.origin_number}</td>
                  <td className="px-2 py-2">
                    <div className="font-semibold">
                      {g.is_exact && <span className="text-[var(--mh-ok)] mr-1">✅</span>}
                      {g.name}
                    </div>
                    <TableEvidenceCell evidence={g.evidence} answers={answers} evidenceMinScore={evidenceMinScore} />
                  </td>
                  <td className="text-right px-2 py-2 tabular-nums font-semibold whitespace-nowrap">
                    {g.is_exact ? (
                      <span className="text-[var(--mh-ok)] font-bold">정확</span>
                    ) : g.score.toFixed(3)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}

