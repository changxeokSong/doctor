import { useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { RecentOutputEntry } from '../api/types'
import { stripCategory } from '../utils/gloss'

function SortTh({
  label, active, dir, onClick, className = '',
}: {
  label: string; active: boolean; dir: 'asc' | 'desc'; onClick: () => void; className?: string
}) {
  return (
    <th className={className} style={{ cursor: 'pointer', userSelect: 'none' }} onClick={onClick}>
      {label}
      {/* 글자를 껐다 켜지 않고 항상 렌더링한 채 opacity만 바꾼다 - 없다가 생기면 그 글자의 줄
          높이만큼 헤더 행 높이가 미세하게 바뀌면서 화면이 흔들린다(정렬 클릭할 때마다 재현됨). */}
      <span style={{ display: 'inline-block', width: 10, fontSize: 9, opacity: active ? 1 : 0 }}>
        {dir === 'asc' ? '▲' : '▼'}
      </span>
    </th>
  )
}

function Section({ title, note, children }: { title: string; note?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="card">
      <div className="card-title">{title}</div>
      {children}
      {note && <div className="card-note">{note}</div>}
    </div>
  )
}

const PRIORITY_BADGE: Record<'gloss' | 'category', { label: string; className: string; title: string }> = {
  gloss: {
    label: '표제어 우선',
    className: 'priority-badge priority-badge-gloss',
    title: '이 표제어 자체가 이 세부분류의 우선순위 목록에 이름(ID)으로 직접 등록되어 있어, 점수보다 앞선 순서로 올라왔습니다.',
  },
  category: {
    label: '카테고리 우선',
    className: 'priority-badge priority-badge-category',
    title: '이 표제어의 이름은 목록에 없지만, 이 표제어가 속한 분류(카테고리) 자체가 이 세부분류의 우선순위 목록에 있어 점수보다 앞선 순서로 올라왔습니다.',
  },
}

/** 163.239.25.74:8777의 catalog.html "최근 출력 글로스 · ID 목록"과 같은 형태 — 최근 결과
 * 이력 전체가 아니라 가장 최근 실행 1건만, 표(.compact-table)로 보여준다. */
function RecentOutputs({ entries }: { entries: RecentOutputEntry[] }) {
  // 기본은 백엔드 순서(세부분류 우선순위 반영) - 스코어 헤더를 누르면 순수 점수순으로 토글한다.
  const [byScore, setByScore] = useState(false)

  if (entries.length === 0) {
    return <div className="empty-note">추천 화면에서 질문을 실행하면 여기에 최근 출력 목록이 표시됩니다.</div>
  }
  const latest = entries[0]
  const rows = byScore ? [...latest.glosses].sort((a, b) => b.score - a.score) : latest.glosses
  const anyPrioritized = latest.glosses.some((g) => g.prioritized)

  return (
    <>
      <div className="latest-question">{latest.question} · {latest.stage} / {latest.subCategory}</div>
      <div className="table-scroll">
        <table className="table compact-table">
          <thead>
            <tr>
              <th>#</th><th>글로스</th><th>ID</th>
              <SortTh label="스코어" active={byScore} dir="desc" onClick={() => setByScore(!byScore)} />
            </tr>
          </thead>
          <tbody>
            {rows.map((g, i) => {
              const badge = g.priorityKind ? PRIORITY_BADGE[g.priorityKind] : null
              return (
                <tr key={g.glossId}>
                  <td className="row-number">{i + 1}</td>
                  <td className="gl">
                    {g.keyword}
                    {badge && <> <span className={badge.className} title={badge.title}>{badge.label}</span></>}
                  </td>
                  <td>{g.glossId}</td>
                  <td>{g.score.toFixed(2)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {anyPrioritized && (
        <div className="card-note">
          기본 순서는 점수순이 아니라 세부분류별 우선순위 규칙을 먼저 따릅니다. "표제어 우선"은 이 표제어의
          이름(ID)이 이 세부분류용으로 미리 정해둔 목록에 직접 올라있는 경우이고, "카테고리 우선"은 이름은
          그 목록에 없지만 이 표제어가 속한 분류가 목록에 있는 경우입니다 — 둘 다 사람이 세부분류마다 미리
          지정해둔 것으로, 지금은 49개 세부분류 중 8개(location, side, chief_complaint, surgery_site,
          pain_score, quality, prior_treatment, treatment_choice)에만 있습니다. "스코어" 헤더를 누르면
          순수 점수 내림차순으로, 다시 누르면 원래 순서로 돌아갑니다.
        </div>
      )}
    </>
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
    const rows = q
      ? dictQuery.data.glosses.filter(
          (g) => g.name.includes(q) || String(g.origin_number).includes(q) || stripCategory(g.category).includes(q),
        )
      : dictQuery.data.glosses
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
    <>
      <Section
        title="전체 현황"
        note={
          <>
            <div>의미 부류: 표제어가 속한 의미 영역 (신체·시간·감정 등) — 아래 "전체 글로스 DB" 표의 "분류" 컬럼과 같은 값</div>
            <div>배정: 구체적인 분류 있음 / 미배정: "기타"로만 남음</div>
            <div>질문/답변 수는 검색에 실제 쓰이는 원본 코퍼스(증강 제외) 기준입니다.</div>
          </>
        }
      >
        <div className="stat-grid">
          <div className="stat-card"><span>전체 글로스</span><strong>{total}</strong><small>개</small></div>
          <div className="stat-card"><span>의미 부류 배정</span><strong>{total - unassigned}</strong><small>개</small></div>
          <div className="stat-card"><span>미배정 글로스</span><strong>{unassigned}</strong><small>개</small></div>
          <div className="stat-card"><span>문진단계</span><strong>{stageCount}</strong><small>개</small></div>
          <div className="stat-card"><span>세부분류</span><strong>{subRows.length}</strong><small>개</small></div>
          <div className="stat-card"><span>질문 / 답변</span><strong>{questionTotal} / {answerTotal}</strong></div>
        </div>
      </Section>

      <Section title="최근 출력 글로스 · ID 목록" note="최근 추천 결과와 별도로 글로스, ID, 스코어만 확인합니다.">
        <RecentOutputs entries={recentOutputs} />
      </Section>

      <Section
        title={`모든 문진단계·세부분류 (${subRows.length}개)`}
        note={subRows.length > 0 && (
          <>
            <div>
              주/보조 의미 부류는 세부분류 {subRows.length}개 이름만 보고 LLM이 도메인 상식으로 한 번 추정해
              채운 고정값입니다 — 코퍼스 통계나 별도 추출 모델로 검증한 값이 아니며, 질문마다 실행 중
              계산되지도 않습니다.
            </div>
            <div>위 "전체 현황"의 의미 부류(글로스 자체의 분류)와는 다른 축입니다.</div>
          </>
        )}
      >
        {subStatsQuery.isPending && <div className="empty-note">불러오는 중...</div>}
        {subStatsQuery.isError && <div className="notice error">불러오기 실패 — {(subStatsQuery.error as Error).message}</div>}
        {subRows.length > 0 && (
          <div className="table-scroll stage-table-scroll">
            <table className="table stage-table">
              <thead>
                <tr>
                  <th>#</th><th>문진단계</th><th>세부분류</th><th>질문</th><th>답변</th>
                  <th>주 의미 부류</th><th>보조 의미 부류</th>
                </tr>
              </thead>
              <tbody>
                {subRows.map((r, i) => (
                  <tr key={`${r.단계}-${r.세부분류}`}>
                    <td className="row-number">{i + 1}</td>
                    <td><strong>{r.단계}</strong></td>
                    <td>{r.세부분류}</td>
                    <td>{r.질문}</td>
                    <td>{r.답변}</td>
                    <td>{r.primary_role || '-'}</td>
                    <td>{r.secondary_roles.length > 0 ? r.secondary_roles.join(', ') : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <div className="card">
        <div className="card-title">전체 글로스 DB ({filtered.length}개{search && ` / ${total}개 중`})</div>
        <div className="catalog-toolbar">
          <input
            aria-label="표제어 검색"
            type="search"
            placeholder="글로스, ID, 분류 검색"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <span>{filtered.length}개 표시</span>
        </div>
        {dictQuery.isPending && <div className="empty-note">불러오는 중...</div>}
        {dictQuery.isError && <div className="notice error">불러오기 실패 — {(dictQuery.error as Error).message}</div>}
        {dictQuery.data && (
          <div ref={dbScrollRef} className="table-scroll catalog-table-scroll">
            <table className="table catalog-table">
              <thead>
                <tr>
                  <th>#</th>
                  <SortTh label="ID" active={sortKey === 'origin_number'} dir={sortDir} onClick={() => toggleSort('origin_number')} />
                  <SortTh label="글로스" active={sortKey === 'name'} dir={sortDir} onClick={() => toggleSort('name')} />
                  <th>유의어</th>
                  <SortTh label="분류" active={sortKey === 'category'} dir={sortDir} onClick={() => toggleSort('category')} />
                </tr>
              </thead>
              <tbody>
                {filtered.map((g, i) => {
                  const [first, ...rest] = g.name.split(',')
                  return (
                    <tr key={g.origin_number}>
                      <td className="row-number">{i + 1}</td>
                      <td>{g.origin_number}</td>
                      <td className="gl">{first}</td>
                      <td>{rest.join(', ') || '-'}</td>
                      <td>{stripCategory(g.category)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
