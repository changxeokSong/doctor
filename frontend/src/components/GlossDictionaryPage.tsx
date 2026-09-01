import { useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { RecentOutputEntry } from '../api/types'

const CATEGORY_PREFIX = '일상생활 수어 > '
const stripCategory = (c: string) => (c.startsWith(CATEGORY_PREFIX) ? c.slice(CATEGORY_PREFIX.length) : c)

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[var(--mh-surface-2)] rounded-[10px] px-[15px] py-[13px] min-h-[72px] flex flex-col justify-center gap-1">
      <span className="text-lg font-extrabold tabular-nums whitespace-nowrap">{value}</span>
      <span className="text-xs text-[var(--mh-muted-2)]">{label}</span>
    </div>
  )
}

function SortTh({
  label, active, dir, onClick, align = 'left', className = '',
}: {
  label: string; active: boolean; dir: 'asc' | 'desc'; onClick: () => void; align?: 'left' | 'right'; className?: string
}) {
  return (
    <th
      className={
        `font-bold px-3 py-2 whitespace-nowrap cursor-pointer select-none hover:text-[var(--mh-text)] ${className} ` +
        (align === 'right' ? 'text-right' : 'text-left')
      }
      onClick={onClick}
    >
      <span className={'inline-flex items-center gap-1' + (align === 'right' ? ' flex-row-reverse' : '')}>
        {label}
        <span className="text-[9px] w-2.5 inline-block text-[var(--mh-accent)]">{active ? (dir === 'asc' ? '▲' : '▼') : ''}</span>
      </span>
    </th>
  )
}

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div className="bg-[var(--mh-surface)] border border-[var(--mh-border)] rounded-xl p-[18px] shadow-[var(--mh-card-shadow)]">
      <div className="text-[13px] font-extrabold mb-1">{title}</div>
      {note && <div className="text-xs text-[var(--mh-muted-2)] mb-3">{note}</div>}
      {children}
    </div>
  )
}

function timeAgo(ts: number): string {
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000))
  if (sec < 60) return '방금'
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`
  if (sec < 86400) return `${Math.floor(sec / 3600)}시간 전`
  return `${Math.floor(sec / 86400)}일 전`
}

function RecentOutputs({ entries }: { entries: RecentOutputEntry[] }) {
  if (entries.length === 0) {
    return <div className="text-xs text-[var(--mh-muted-2)]">추천 화면에서 질문을 실행하면 여기에 최근 결과가 쌓입니다.</div>
  }
  return (
    <div className="flex flex-col gap-2.5 max-h-[320px] overflow-auto">
      {entries.map((e, i) => (
        <div key={i} className="border border-[var(--mh-border)] rounded-lg px-3 py-2.5">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[13px] font-semibold truncate">{e.question}</span>
            <span className="text-[11px] text-[var(--mh-muted-2)] shrink-0">{timeAgo(e.timestamp)}</span>
          </div>
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {e.glosses.length === 0 && <span className="text-xs text-[var(--mh-muted-2)]">표현 가능한 글로스 없음</span>}
            {e.glosses.map((g) => (
              <span
                key={g.origin_number}
                className={
                  'text-xs font-semibold rounded-full px-2.5 py-1 ' +
                  (g.is_exact ? 'bg-[#1a7f37] text-white' : 'bg-[var(--mh-surface-2)] border border-[var(--mh-border)]')
                }
              >
                {g.name.split(',')[0]} <span className="opacity-70 tabular-nums">{g.origin_number}</span>
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function GlossDictionaryPage({ recentOutputs }: { recentOutputs: RecentOutputEntry[] }) {
  const dictQuery = useQuery({ queryKey: ['gloss-dictionary'], queryFn: api.glossDictionary })
  const subStatsQuery = useQuery({ queryKey: ['subcategory-stats'], queryFn: api.subcategoryStats })
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<'origin_number' | 'name' | 'category'>('origin_number')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const dbScrollRef = useRef<HTMLDivElement>(null)

  function toggleSort(key: typeof sortKey) {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(key)
      setSortDir('asc')
    }
    // 스크롤이 아래로 내려간 채로 재정렬하면 눈에 보이는 행이 갑자기 바뀌어 "위아래로 움직이는"
    // 것처럼 보인다 - 정렬 기준이 바뀔 때마다 맨 위로 되돌린다.
    dbScrollRef.current?.scrollTo({ top: 0 })
  }

  const filtered = useMemo(() => {
    if (!dictQuery.data) return []
    const q = search.trim()
    const rows = q ? dictQuery.data.glosses.filter((g) => g.name.includes(q) || String(g.origin_number).includes(q)) : dictQuery.data.glosses
    const sorted = [...rows].sort((a, b) => {
      const cmp =
        sortKey === 'origin_number' ? a.origin_number - b.origin_number
        : sortKey === 'name' ? a.name.localeCompare(b.name, 'ko')
        : stripCategory(a.category).localeCompare(stripCategory(b.category), 'ko')
      return sortDir === 'asc' ? cmp : -cmp
    })
    return sorted
  }, [dictQuery.data, search, sortKey, sortDir])

  const unassigned = dictQuery.data?.categories.find((c) => stripCategory(c.category) === '기타')?.count ?? 0
  const total = dictQuery.data?.total ?? 0
  const subRows = subStatsQuery.data?.rows ?? []
  const stageCount = new Set(subRows.map((r) => r.단계)).size
  const questionTotal = subRows.reduce((s, r) => s + r.질문, 0)
  const answerTotal = subRows.reduce((s, r) => s + r.답변, 0)

  return (
    <div className="flex flex-col gap-[18px]">
      <Section title="전체 현황">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          <StatCard label="전체 글로스" value={`${total}개`} />
          <StatCard label="의미 부류 배정" value={`${total - unassigned}개`} />
          <StatCard label="미배정 글로스" value={`${unassigned}개`} />
          <StatCard label="문진단계" value={`${stageCount}개`} />
          <StatCard label="세부분류" value={`${subRows.length}개`} />
          <StatCard label="질문 / 답변" value={`${questionTotal} / ${answerTotal}`} />
        </div>
      </Section>

      <Section title="최근 출력 글로스" note="추천 화면 실행 결과가 최신순으로 쌓입니다(이 브라우저에만 저장됨, 최대 20건).">
        <RecentOutputs entries={recentOutputs} />
      </Section>

      <Section title={`문진단계 · 세부분류 (${subRows.length}개)`}>
        {subStatsQuery.isPending && <div className="text-xs text-[var(--mh-muted-2)]">불러오는 중...</div>}
        {subStatsQuery.isError && <div className="text-xs text-red-600">불러오기 실패 — {(subStatsQuery.error as Error).message}</div>}
        {subRows.length > 0 && (
          <div className="overflow-auto max-h-[420px] border border-[var(--mh-border)] rounded-lg">
            <table className="w-full text-sm table-fixed">
              <colgroup>
                <col className="w-10" />
                <col className="w-[30%]" />
                <col />
                <col className="w-16" />
                <col className="w-16" />
              </colgroup>
              <thead className="sticky top-0 bg-[var(--mh-surface-2)]">
                <tr className="text-xs text-[var(--mh-muted)] uppercase tracking-wide">
                  <th className="text-right font-bold px-2 py-2">#</th>
                  <th className="text-left font-bold px-3 py-2">문진단계</th>
                  <th className="text-left font-bold px-3 py-2">세부분류</th>
                  <th className="text-right font-bold px-3 py-2">질문</th>
                  <th className="text-right font-bold px-3 py-2">답변</th>
                </tr>
              </thead>
              <tbody>
                {subRows.map((r, i) => (
                  <tr key={`${r.단계}-${r.세부분류}`} className="border-t border-[var(--mh-border)]">
                    <td className="text-right px-2 py-2 tabular-nums text-[var(--mh-muted-2)]">{i + 1}</td>
                    <td className="px-3 py-2">{r.단계}</td>
                    <td className="px-3 py-2 font-mono text-xs text-[var(--mh-muted)]">{r.세부분류}</td>
                    <td className="text-right px-3 py-2 tabular-nums">{r.질문}</td>
                    <td className="text-right px-3 py-2 tabular-nums">{r.답변}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <div className="bg-[var(--mh-surface)] border border-[var(--mh-border)] rounded-xl overflow-hidden shadow-[var(--mh-card-shadow)]">
        <div className="p-[18px] pb-3">
          <div className="text-[13px] font-extrabold mb-3">전체 글로스 DB ({filtered.length}개{search && ` / ${total}개 중`})</div>
          <input
            aria-label="표제어 검색"
            className="w-full border-[1.5px] border-[var(--mh-border)] rounded-[10px] px-[15px] py-2.5 text-sm outline-none focus:border-[var(--mh-accent)]"
            placeholder="표제어 이름 또는 인덱스로 검색"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {dictQuery.isPending && <div className="px-[18px] pb-[18px] text-sm text-[var(--mh-muted)]">불러오는 중...</div>}
        {dictQuery.isError && <div className="px-[18px] pb-[18px] text-sm text-red-600">불러오기 실패 — {(dictQuery.error as Error).message}</div>}
        {dictQuery.data && (
          <div ref={dbScrollRef} className="mx-[18px] mb-[18px] overflow-auto max-h-[420px] border border-[var(--mh-border)] rounded-lg">
            <table className="w-full text-sm table-fixed">
              <colgroup>
                <col className="w-20" />
                <col />
                <col className="w-[38%]" />
              </colgroup>
              <thead className="sticky top-0 bg-[var(--mh-surface-2)]">
                <tr className="text-xs text-[var(--mh-muted)] uppercase tracking-wide">
                  <SortTh
                    label="인덱스" align="right"
                    active={sortKey === 'origin_number'} dir={sortDir} onClick={() => toggleSort('origin_number')}
                  />
                  <SortTh label="표제어" active={sortKey === 'name'} dir={sortDir} onClick={() => toggleSort('name')} />
                  <SortTh label="분류" active={sortKey === 'category'} dir={sortDir} onClick={() => toggleSort('category')} />
                </tr>
              </thead>
              <tbody>
                {filtered.map((g) => (
                  <tr key={g.origin_number} className="border-t border-[var(--mh-border)]">
                    <td className="text-right px-3 py-2 tabular-nums text-[var(--mh-muted-2)] whitespace-nowrap">{g.origin_number}</td>
                    <td className="px-3 py-2 font-semibold">{g.name}</td>
                    <td className="px-3 py-2 text-[var(--mh-muted)]">{stripCategory(g.category)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
