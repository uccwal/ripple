import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { GraphNode, RetryLoop, RunState, Shock, Step } from '@/api/types'
import { formatShockInput, parseShockInput, roundTo, shockDigits } from '@/utils/format'
import { isActiveStatus, useLiveRunsStore } from './liveRuns'
import type { LoadState } from './types'

export type RunTab = 'path' | 'scen' | 'result' | 'report'
export const RUN_TABS: readonly RunTab[] = ['path', 'scen', 'result', 'report']

export function isRunTab(v: unknown): v is RunTab {
  return typeof v === 'string' && (RUN_TABS as readonly string[]).includes(v)
}

export interface DraftRow {
  shock: Shock
  text: string
  parsed: number | null
  invalid: boolean
  changed: boolean
}

/** 기본 선택 노드: 거시 변수 중 확신도 높음 → 거시 변수 첫 노드 → 첫 노드 */
export function defaultNodeId(nodes: GraphNode[]): string | null {
  const macro = nodes.filter((n) => n.layer === 'macro')
  return (macro.find((n) => n.confidence === 'high') ?? macro[0] ?? nodes[0])?.id ?? null
}

/** S3 분석 워크스페이스에서 보고 있는 실행 하나의 상태 */
export const useRunStore = defineStore('run', () => {
  const live = useLiveRunsStore()

  const runId = ref<string | null>(null)
  const run = ref<RunState | null>(null)
  const state = ref<LoadState>('idle')
  const error = ref<string | null>(null)

  const activeTab = ref<RunTab>('path')
  const selectedNodeId = ref<string | null>(null)
  const expandedStep = ref<number | null>(null)
  /** variable → 입력 문자열 */
  const draftShocks = ref<Record<string, string>>({})
  const recalcPending = ref(false)
  const recalcError = ref<string | null>(null)

  let loadSeq = 0

  /* ---------- 실행 상태 (SSE 우선, 없으면 RunState) ---------- */

  const liveRun = computed(() => (runId.value ? live.runs[runId.value] ?? null : null))
  const status = computed(() => liveRun.value?.status ?? run.value?.status ?? null)
  const isActive = computed(() => status.value !== null && isActiveStatus(status.value))
  const steps = computed<Step[]>(() => liveRun.value?.steps ?? run.value?.steps ?? [])
  const retryLoops = computed<RetryLoop[]>(() => liveRun.value?.retryLoops ?? run.value?.retry_loops ?? [])
  const elapsedMs = computed<number | null>(() => {
    if (runId.value && liveRun.value && isActive.value) return live.elapsedOf(runId.value)
    return run.value?.elapsed_ms ?? liveRun.value?.elapsedMs ?? null
  })
  const currentText = computed(() => {
    if (liveRun.value?.current) return liveRun.value.current
    const s = steps.value.find((x) => x.status === 'running')
    if (!s) return '준비 중'
    return `${s.agent} — ${s.desc}${s.attempt > 1 ? ` (${s.attempt}차 시도)` : ''}`
  })

  /* ---------- 시나리오 초안 ---------- */

  const shocks = computed<Shock[]>(() => run.value?.scenario?.shocks ?? [])

  const draftRows = computed<DraftRow[]>(() =>
    shocks.value.map((shock) => {
      const text = draftShocks.value[shock.variable] ?? formatShockInput(shock.change, shock.unit)
      const parsed = parseShockInput(text)
      const applied = roundTo(shock.change, shockDigits(shock.unit))
      const changed = parsed !== null && Math.abs(parsed - applied) > 1e-9
      return { shock, text, parsed, invalid: parsed === null, changed }
    }),
  )
  const isDirty = computed(() => draftRows.value.some((r) => r.changed))
  const hasInvalid = computed(() => draftRows.value.some((r) => r.invalid))
  const canRecalc = computed(() => isDirty.value && !hasInvalid.value && !recalcPending.value)

  function resetDraft(): void {
    draftShocks.value = Object.fromEntries(shocks.value.map((s) => [s.variable, formatShockInput(s.change, s.unit)]))
    recalcError.value = null
  }

  function setDraft(variable: string, text: string): void {
    draftShocks.value = { ...draftShocks.value, [variable]: text }
  }

  /** PATCH /api/runs/{id}/scenario → 새 run_id */
  async function submitRecalc(): Promise<string | null> {
    if (!run.value || !canRecalc.value) return null
    recalcPending.value = true
    recalcError.value = null
    try {
      const changes = draftRows.value
        .filter((r) => r.changed && r.parsed !== null)
        .map((r) => ({ variable: r.shock.variable, change: r.parsed as number }))
      const res = await api.patchScenario(run.value.run_id, { shocks: changes })
      void live.trackById(res.run_id)
      return res.run_id
    } catch (err) {
      recalcError.value = errorMessage(err)
      return null
    } finally {
      recalcPending.value = false
    }
  }

  /* ---------- 로드 ---------- */

  function applyRun(next: RunState): void {
    const sameRun = run.value?.run_id === next.run_id
    run.value = next
    if (!sameRun || Object.keys(draftShocks.value).length === 0) resetDraft()
    const nodes = next.graph?.nodes ?? []
    if (!selectedNodeId.value || !nodes.some((n) => n.id === selectedNodeId.value)) {
      selectedNodeId.value = defaultNodeId(nodes)
    }
    live.track(next)
  }

  async function load(id: string, tab?: RunTab): Promise<void> {
    const seq = ++loadSeq
    if (runId.value !== id) {
      runId.value = id
      run.value = null
      selectedNodeId.value = null
      expandedStep.value = null
      draftShocks.value = {}
      recalcError.value = null
    }
    state.value = 'loading'
    error.value = null
    try {
      const next = await api.run(id)
      if (seq !== loadSeq) return
      activeTab.value = tab ?? (next.entry === 'scenario' ? 'scen' : 'path')
      applyRun(next)
      state.value = 'ready'
    } catch (err) {
      if (seq !== loadSeq) return
      error.value = errorMessage(err)
      state.value = 'error'
    }
  }

  /** 진행 중이던 실행이 끝나면 전체 결과를 다시 받는다. */
  live.onFinish((finished, id) => {
    if (id !== runId.value) return
    if (finished) applyRun(finished)
    else void load(id, activeTab.value)
  })

  function setTab(tab: RunTab): void {
    activeTab.value = tab
  }

  function selectNode(id: string): void {
    selectedNodeId.value = id
  }

  function toggleStep(idx: number): void {
    expandedStep.value = expandedStep.value === idx ? null : idx
  }

  return {
    runId,
    run,
    state,
    error,
    activeTab,
    selectedNodeId,
    expandedStep,
    draftShocks,
    recalcPending,
    recalcError,
    status,
    isActive,
    steps,
    retryLoops,
    elapsedMs,
    currentText,
    draftRows,
    isDirty,
    hasInvalid,
    canRecalc,
    load,
    setTab,
    selectNode,
    toggleStep,
    setDraft,
    resetDraft,
    submitRecalc,
  }
})
