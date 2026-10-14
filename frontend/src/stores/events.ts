import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { CountryCode, EventSummary, EventType } from '@/api/types'
import type { LoadState } from './types'

export type PeriodDays = 7 | 30 | 90

export interface EventFilters {
  country: CountryCode | 'all'
  type: EventType | 'all'
  period: PeriodDays
}

/** S1 이벤트 목록(필터 적용)과 S2 이벤트 선택 목록(전체) */
export const useEventStore = defineStore('events', () => {
  const filters = ref<EventFilters>({ country: 'all', type: 'all', period: 30 })
  const events = ref<EventSummary[]>([])
  const state = ref<LoadState>('idle')
  const error = ref<string | null>(null)

  const allEvents = ref<EventSummary[]>([])
  const allState = ref<LoadState>('idle')
  const allError = ref<string | null>(null)

  let controller: AbortController | null = null

  async function fetchEvents(): Promise<void> {
    controller?.abort()
    const ctrl = new AbortController()
    controller = ctrl
    state.value = 'loading'
    error.value = null
    const f = filters.value
    try {
      const list = await api.events(
        {
          country: f.country === 'all' ? undefined : f.country,
          type: f.type === 'all' ? undefined : f.type,
          days: f.period,
        },
        ctrl.signal,
      )
      if (controller !== ctrl) return
      events.value = list
      state.value = 'ready'
    } catch (err) {
      if (ctrl.signal.aborted) return
      error.value = errorMessage(err)
      state.value = 'error'
    }
  }

  async function fetchAll(): Promise<void> {
    allState.value = 'loading'
    allError.value = null
    try {
      allEvents.value = await api.events()
      allState.value = 'ready'
    } catch (err) {
      allError.value = errorMessage(err)
      allState.value = 'error'
    }
  }

  watch(filters, () => void fetchEvents(), { deep: true })

  return { filters, events, state, error, fetchEvents, allEvents, allState, allError, fetchAll }
})
