import { useState } from 'react'
import type { RecommendedGloss } from '../api/types'

/** 근거(어느 답변에서 이 키워드가 나와서 이 표제어로 이어졌는지)가 3개를 넘으면 접어두고,
 * "더보기"를 눌러야 나머지가 펼쳐진다 - 표 안에서 텍스트가 무한정 길어지는 걸 막는다.
 * 근거 인정 기준(evidenceMinScore)은 더 이상 고정값이 아니라 backend/pipeline/services.py의
 * _dynamic_evidence_min_score가 이번 요청 점수 분포로 매번 새로 계산해서 내려준다(2026-08-26,
 * 사용자 요청 - "평균 임계값 확인해서 동적으로 정할 수 있냐"). */

/** 근거 문장 안에서 키워드를 찾아 <mark>로 강조한다 - 조윤기 팀 데모(163.239.25.74:8777)의
 * .evidence-sent/mark 스타일을 실제 페이지에서 computed style로 추출해 그대로 옮겼다
 * (배경 #fff3bf, radius 3px, 2026-08-25, 사용자 요청 "UI/UX 완전 똑같이"). */
function HighlightedEvidenceSentence({ answer, keyword }: { answer: string; keyword: string }) {
  const idx = answer.indexOf(keyword)
  if (idx === -1) return <>{answer}</>
  return (
    <>
      {answer.slice(0, idx)}
      <mark className="bg-[#fff3bf] text-inherit rounded-[3px] px-0.5 font-semibold">
        {answer.slice(idx, idx + keyword.length)}
      </mark>
      {answer.slice(idx + keyword.length)}
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
          <HighlightedEvidenceSentence answer={answers[e.answer_index] ?? ''} keyword={e.keyword} />
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

/** 저쪽 .evidence-row(grid, 왼쪽 고정폭 표제어 + 오른쪽 문장들)를 그대로 재현. */
/** 근거 문장은 표제어당 제일 유사도 높은 것 딱 1개만 보여준다(2026-08-26, 사용자 요청 -
 * "근거 문장 하나씩만 나오게"). evidence는 이미 백엔드에서 점수 내림차순 정렬돼 오므로
 * evidence[0]가 최선의 근거다. 나머지 근거까지 다 보고 싶으면 "전체 654개 순위 보기" 표의
 * 근거 칸에서 "더보기"로 볼 수 있다. */
function EvidenceRow({ name, evidence, answers }: { name: string; evidence: RecommendedGloss['evidence']; answers: string[] }) {
  if (evidence.length === 0) return null
  const best = evidence[0]
  return (
    <div className="grid grid-cols-[minmax(96px,168px)_1fr] gap-3 py-[7px] border-b border-[#f7f7fa] last:border-b-0 items-baseline">
      <span className="text-[13px] font-bold text-[var(--mh-ok)] break-all">{name}</span>
      <span className="text-[13px] text-[#3c3c43]">
        <HighlightedEvidenceSentence answer={answers[best.answer_index] ?? ''} keyword={best.keyword} />
      </span>
    </div>
  )
}

/** 답변 여러 개(최대 20개)에 흩어진 대표 키워드를 표제어(원문 인덱스) 기준으로 합친 집계 -
 * 답변마다 따로 보던 걸 표제어 하나당 "어느 답변에서 나왔는지" 근거와 함께 한 표로 본다.
 * 컷 없이 사전 전체(~654개)를 스코어순으로 다 보여준다(2026-08-19, 사용자가 순위를 직접 보고
 * 판단하길 원함 - services.py의 RECOMMENDED_GLOSS_MIN_SCORE 참고). */

/** 조윤기 팀 데모의 .kw/.kw.t1/.t2 색을 참고했다(2026-08-25, styles.css .kw.t1/.t2 computed
 * style에서 추출). 저쪽은 스코어가 1.0/0.8/0.5 중 하나로만 나오는 고정 단계값이라 색 경계가
 * 고정이었는데, 저희는 연속 유사도 + 동적 임계값이라 "임계값 대비 상대 위치"로 3단계를 나눈다
 * (2026-08-26, 사용자 요청 - "임계값 기준으로 색상 표시해달라"): 정확일치(진한 초록) /
 * 임계값과 1.0 사이 중간점 이상(중간 초록) / 임계값 이상 중간점 미만(연한 초록). 임계값
 * 미달은 이미 core 필터에서 아예 빠지므로 여기 안 들어온다. */
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

/** 조윤기 팀 데모의 "핵심 표제어" 표(표제어/인덱스/스코어/의미 부류/근거 키워드와 문장) 형태 -
 * 메인 추천 화면은 알약(pill) 방식을 유지하고, 이 표 형태는 "분석 보기"(AnalysisPanel)
 * 전용으로 뺐다(2026-08-26, 사용자 요청 - "분석보기에서 그래야지, 메인은 원상 복구"). "의미
 * 부류" 칼럼은 저쪽에서 LLM이 질문마다 실시간으로 붙이는 값이라 우리 아키텍처엔 없는
 * 개념이라, 대신 우리가 실제로 가진 값인 예측 세부분류(subLabel)로 채운다. */
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
                      <div><HighlightedEvidenceSentence answer={answers[best.answer_index] ?? ''} keyword={best.keyword} /></div>
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
  // 유사도 중간값(evidenceMinScore~1.0의 중간점, pillTier의 tier 3 경계) 미만인 표제어는
  // 기본적으로 접어두고 "더보기"를 눌러야 펼쳐진다 - 근거가 약한(연한 초록) 표제어까지 전부
  // 알약으로 늘어놓으면 화면이 길어져서 진짜 강한 근거(정확일치·중간값 이상)부터 먼저 보이게
  // 나눈다(2026-08-31, 사용자 요청). 펼침 상태는 알약 목록과 근거 문장 목록이 같이 움직인다.
  // 다만 중간값 이상만으로는 몇 개 안 나오는 질문이 있어(예: 6개) "더보기 누르기 전에도 최소
  // 10개는 보이게" 요청받아, 중간값 이상 개수가 10 미만이면 core(이미 점수순 정렬됨) 앞에서부터
  // 채워 최소 MIN_VISIBLE개를 보장한다 - 중간값 이상 표제어가 10개를 넘으면 그만큼 다 보여준다
  // (강한 근거를 굳이 접어두지 않음).
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
  const aboveMidpointCount = core.filter((g) => pillTier(g, evidenceMinScore) !== 3).length
  const visibleCount = Math.max(MIN_VISIBLE, aboveMidpointCount)
  const primary = core.slice(0, visibleCount)
  const secondary = core.slice(visibleCount)
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
            정확일치이거나, 나머지 중 유사도 상위 15%에 든 표제어만 아래 색깔 표시에 나옵니다
            (이번 질문의 점수 분포로 매번 다시 계산됨 — 자세한 기준은 "분석 보기"에서 확인).
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

