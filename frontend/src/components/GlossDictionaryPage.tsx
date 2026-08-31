import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

// 세부분류/문진단계별 매핑은 고정 테이블이 없어(질문마다 즉석 임베딩 검색) 여기 없음.
export function GlossDictionaryPage() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ['gloss-dictionary'],
    queryFn: api.glossDictionary,
  })
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    if (!data) return []
    const q = search.trim()
    if (!q) return data.glosses
    return data.glosses.filter((g) => g.name.includes(q) || String(g.origin_number).includes(q))
  }, [data, search])

  if (isPending) return <div className="text-sm text-[var(--mh-muted)]">불러오는 중...</div>
  if (isError) return <div className="text-sm text-red-600">불러오기 실패 — {(error as Error).message}</div>

  return (
    <div className="flex flex-col gap-[18px]">
      <div className="bg-[var(--mh-surface)] border border-[var(--mh-border)] rounded-xl p-[18px] shadow-[var(--mh-card-shadow)]">
        <div className="text-[13px] font-extrabold mb-3">표제어 사전 통계</div>
        <div className="bg-[var(--mh-surface-2)] rounded-[10px] px-[15px] py-[13px] text-[13px] text-[#3c3c43]">
          <div>총 표제어 수: <span className="font-semibold">{data!.total}개</span></div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {data!.categories.map((c) => (
            <span
              key={c.category}
              className="text-xs font-semibold bg-[var(--mh-surface-2)] border border-[var(--mh-border)] rounded-full px-3 py-1.5"
            >
              {c.category} <span className="text-[var(--mh-muted-2)] font-normal">{c.count}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="bg-[var(--mh-surface)] border border-[var(--mh-border)] rounded-xl overflow-hidden shadow-[var(--mh-card-shadow)]">
        <div className="p-[18px] pb-3">
          <div className="text-[13px] font-extrabold mb-3">전체 목록 ({filtered.length}개{search && ` / ${data!.total}개 중`})</div>
          <input
            className="w-full border-[1.5px] border-[var(--mh-border)] rounded-[10px] px-[15px] py-2.5 text-sm outline-none focus:border-[var(--mh-accent)]"
            placeholder="표제어 이름 또는 인덱스로 검색"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="overflow-auto max-h-[calc(100vh-14rem)]">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-[var(--mh-surface-2)]">
              <tr className="text-xs text-[var(--mh-muted)] uppercase tracking-wide">
                <th className="w-20 text-right font-bold px-3 py-2 whitespace-nowrap">인덱스</th>
                <th className="text-left font-bold px-3 py-2">표제어</th>
                <th className="text-left font-bold px-3 py-2">분류</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((g) => (
                <tr key={g.origin_number} className="border-t border-[var(--mh-border)]">
                  <td className="text-right px-3 py-2 tabular-nums text-[var(--mh-muted-2)] whitespace-nowrap">{g.origin_number}</td>
                  <td className="px-3 py-2 font-semibold">{g.name}</td>
                  <td className="px-3 py-2 text-[var(--mh-muted)]">{g.category}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
