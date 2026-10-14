import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { PortfolioDetail, PortfolioSummary } from '@/api/types'
import type { LoadState } from './types'

/** S2 포트폴리오 선택, S4 구성 화면 */
export const usePortfolioStore = defineStore('portfolios', () => {
  const list = ref<PortfolioSummary[]>([])
  const listState = ref<LoadState>('idle')
  const listError = ref<string | null>(null)

  const selectedId = ref<string | null>(null)
  const details = ref<Record<string, PortfolioDetail>>({})
  const detailState = ref<LoadState>('idle')
  const detailError = ref<string | null>(null)

  const selected = computed(() => (selectedId.value ? details.value[selectedId.value] ?? null : null))
  const holdings = computed(() => selected.value?.holdings ?? [])

  async function loadList(): Promise<void> {
    if (listState.value === 'loading') return
    listState.value = 'loading'
    listError.value = null
    try {
      list.value = await api.portfolios()
      listState.value = 'ready'
      if (!selectedId.value || !list.value.some((p) => p.portfolio_id === selectedId.value)) {
        selectedId.value = list.value[0]?.portfolio_id ?? null
      }
    } catch (err) {
      listError.value = errorMessage(err)
      listState.value = 'error'
    }
  }

  async function loadDetail(id: string): Promise<void> {
    if (details.value[id]) {
      detailState.value = 'ready'
      return
    }
    detailState.value = 'loading'
    detailError.value = null
    try {
      const d = await api.portfolio(id)
      details.value[id] = d
      if (selectedId.value === id) detailState.value = 'ready'
    } catch (err) {
      if (selectedId.value !== id) return
      detailError.value = errorMessage(err)
      detailState.value = 'error'
    }
  }

  function select(id: string): void {
    selectedId.value = id
    void loadDetail(id)
  }

  return { list, listState, listError, selectedId, selected, holdings, details, detailState, detailError, loadList, loadDetail, select }
})
