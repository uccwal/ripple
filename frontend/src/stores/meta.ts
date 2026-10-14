import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { Meta } from '@/api/types'
import type { LoadState } from './types'

/** GET /api/meta — 상단 바 합성 데이터 배지, S1 수집 요약, 모델 표기 */
export const useMetaStore = defineStore('meta', () => {
  const meta = ref<Meta | null>(null)
  const state = ref<LoadState>('idle')
  const error = ref<string | null>(null)

  async function load(): Promise<void> {
    state.value = 'loading'
    error.value = null
    try {
      meta.value = await api.meta()
      state.value = 'ready'
    } catch (err) {
      error.value = errorMessage(err)
      state.value = 'error'
    }
  }

  return { meta, state, error, load }
})
