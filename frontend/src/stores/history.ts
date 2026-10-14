import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { RunListItem } from '@/api/types'
import type { LoadState } from './types'

/** GET /api/runs — S6 실행 이력, S1 최근 분석 */
export const useHistoryStore = defineStore('history', () => {
  const runs = ref<RunListItem[]>([])
  const state = ref<LoadState>('idle')
  const error = ref<string | null>(null)

  async function load(): Promise<void> {
    // 이미 데이터가 있으면 스켈레톤 없이 조용히 갱신한다.
    if (state.value !== 'ready') state.value = 'loading'
    error.value = null
    try {
      runs.value = await api.runs()
      state.value = 'ready'
    } catch (err) {
      error.value = errorMessage(err)
      state.value = 'error'
    }
  }

  return { runs, state, error, load }
})
