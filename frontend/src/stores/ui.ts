import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface CalcPanelTarget {
  runId: string
  /** calc-log entries 키: pnl, amt, range, model, reg, h:{asset}, fc:{factor}, f:{factor} */
  key: string
}

export interface Toast {
  id: number
  message: string
}

/** 토스트 노출 시간 (README: 3.2초 후 사라짐) */
export const TOAST_MS = 3200

export const useUiStore = defineStore('ui', () => {
  const calcPanel = ref<CalcPanelTarget | null>(null)
  const toast = ref<Toast | null>(null)
  let toastTimer: ReturnType<typeof setTimeout> | undefined
  let toastSeq = 0

  function openCalc(runId: string, key: string): void {
    calcPanel.value = { runId, key }
  }

  function closeCalc(): void {
    calcPanel.value = null
  }

  function showToast(message: string): void {
    clearTimeout(toastTimer)
    toast.value = { id: ++toastSeq, message }
    toastTimer = setTimeout(() => {
      toast.value = null
    }, TOAST_MS)
  }

  return { calcPanel, toast, openCalc, closeCalc, showToast }
})
