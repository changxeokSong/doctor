import { useState } from 'react'

const PREFIX = 'mh-settings:'

function readStored<T>(key: string, fallback: T, isValid?: (v: unknown) => boolean): T {
  try {
    const raw = localStorage.getItem(PREFIX + key)
    if (raw === null) return fallback
    const parsed = JSON.parse(raw)  // 타입이 다른 저장값도 통과시키므로 isValid로 한 번 더 검증
    return !isValid || isValid(parsed) ? (parsed as T) : fallback
  } catch {
    return fallback
  }
}

/** useState처럼 쓰되 localStorage에 자동 저장 — 새로고침해도 값이 유지된다.
 * isValid를 주면 저장된 값의 타입/범위를 검증하고, 안 맞으면 fallback을 쓴다. */
export function usePersistedState<T>(key: string, fallback: T, isValid?: (v: unknown) => boolean) {
  const [value, setValue] = useState<T>(() => readStored(key, fallback, isValid))

  function set(next: T) {
    setValue(next)
    try {
      localStorage.setItem(PREFIX + key, JSON.stringify(next))
    } catch {
      // localStorage 접근 불가(프라이빗 모드 등) - 저장 실패는 조용히 무시, 이번 세션 동안은 정상 동작
    }
  }

  return [value, set] as const
}
