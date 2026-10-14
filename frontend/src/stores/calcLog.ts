import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { CalcLog } from '@/api/types'
import type { LoadState } from './types'

interface CacheEntry {
  state: LoadState
  data: CalcLog | null
  error: string | null
}

/** GET /api/runs/{id}/calc-log 결과를 실행별로 캐시한다 (S5 패널). */
export const useCalcLogStore = defineStore('calcLog', () => {
  const byRun = ref<Record<string, CacheEntry>>({})
  const inflight = new Map<string, Promise<void>>()

  function entry(runId: string): CacheEntry {
    return byRun.value[runId] ?? { state: 'idle', data: null, error: null }
  }

  function load(runId: string, force = false): Promise<void> {
    const cached = byRun.value[runId]
    if (!force && cached?.state === 'ready') return Promise.resolve()
    const pending = inflight.get(runId)
    if (pending) return pending

    byRun.value[runId] = { state: 'loading', data: cached?.data ?? null, error: null }
    const p = api
      .calcLog(runId)
      .then((data) => {
        byRun.value[runId] = { state: 'ready', data, error: null }
      })
      .catch((err: unknown) => {
        byRun.value[runId] = { state: 'error', data: null, error: errorMessage(err) }
      })
      .finally(() => inflight.delete(runId))
    inflight.set(runId, p)
    return p
  }

  /** 실행이 다시 계산되면(재계산은 새 run이므로 보통 불필요) 캐시를 비운다. */
  function invalidate(runId: string): void {
    delete byRun.value[runId]
  }

  return { byRun, entry, load, invalidate }
})
