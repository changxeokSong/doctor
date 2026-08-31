import { useState } from 'react'

const PREFIX = 'mh-settings:'

function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(PREFIX + key)
    return raw === null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

/** useState처럼 쓰되 localStorage에 자동 저장 — 새로고침해도 값이 유지된다. */
export function usePersistedState<T>(key: string, fallback: T) {
  const [value, setValue] = useState<T>(() => readStored(key, fallback))

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
