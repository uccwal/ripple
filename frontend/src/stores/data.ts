import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { CollectRequest, DataStatus } from '@/api/types'
import type { LoadState } from './types'

/** GET /api/data/status — S7 데이터 관리. 수집 진행 폴링·자동 갱신은 화면이 담당한다. */
export const useDataStore = defineStore('data', () => {
  const status = ref<DataStatus | null>(null)
  const state = ref<LoadState>('idle')
  /** 첫 로드 실패 (화면 전체 오류 상태) */
  const error = ref<string | null>(null)
  /** 데이터가 있는 상태에서 조용히 갱신하다 실패한 경우 (화면은 유지) */
  const refreshError = ref<string | null>(null)
  const loadedAt = ref(0)

  const running = computed(() => status.value?.collect.running ?? false)

  async function load({ reset = false }: { reset?: boolean } = {}): Promise<void> {
    const quiet = state.value === 'ready' && !reset
    if (!quiet) {
      state.value = 'loading'
      error.value = null
    }
    try {
      status.value = await api.getDataStatus()
      loadedAt.value = Date.now()
      refreshError.value = null
      state.value = 'ready'
    } catch (err) {
      if (quiet) {
        refreshError.value = errorMessage(err)
      } else {
        error.value = errorMessage(err)
        state.value = 'error'
      }
    }
  }

  async function startCollect(token: string, body: CollectRequest): Promise<void> {
    await api.startCollect(token, body)
  }

  return { status, state, error, refreshError, loadedAt, running, load, startCollect }
})
