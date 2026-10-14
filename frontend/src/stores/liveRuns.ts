import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, streamUrl } from '@/api/client'
import { STREAM_EVENTS } from '@/api/types'
import type { RetryLoop, RunState, RunStatus, Step, StreamPayload } from '@/api/types'
import { useHistoryStore } from './history'
import { useUiStore } from './ui'

/** 진행 중인 실행의 실시간 상태 (SSE로 갱신) */
export interface LiveRun {
  runId: string
  title: string
  parentRunId: string | null
  status: RunStatus
  /** 서버가 마지막으로 알려 준 경과 시간 */
  elapsedMs: number
  /** elapsedMs를 받은 로컬 시각 (Date.now) — 이후는 로컬 시계로 0.1초 단위 진행 */
  anchorAt: number
  current: string | null
  steps: Step[]
  retryLoops: RetryLoop[]
  startedAt: number
}

type FinishListener = (run: RunState | null, runId: string) => void

export const isActiveStatus = (s: RunStatus): boolean => s === 'queued' || s === 'running'

/**
 * 계약서의 5개 이벤트 + 연결 직후 현재 상태를 한 번 보내는 `snapshot`
 * (백엔드 구현이 보낸다. 형태는 다른 이벤트와 같다).
 */
const LISTEN_EVENTS = [...STREAM_EVENTS, 'snapshot'] as const

const TICK_MS = 100
const POLL_MS = 1500
/** EventSource 자동 재연결이 이만큼 연속 실패하면 폴링으로 전환 */
const MAX_STREAM_ERRORS = 3

/**
 * 이 세션에서 시작했거나 열어 본 "진행 중" 실행을 추적한다.
 * - 실행마다 EventSource 하나 (/api/runs/{id}/stream). 화면을 떠나도 유지되어
 *   상단 바 실행 중 pill과 완료 토스트가 어느 화면에서나 동작한다.
 * - SSE가 끊기면 GET /api/runs/{id} 폴링으로 대체한다.
 * - run_finished 수신 → 전체 RunState 재조회 → 리스너 통지 · 토스트.
 */
export const useLiveRunsStore = defineStore('liveRuns', () => {
  const runs = ref<Record<string, LiveRun>>({})
  const now = ref(Date.now())

  const sources = new Map<string, EventSource>()
  const pollers = new Map<string, ReturnType<typeof setInterval>>()
  const errorCounts = new Map<string, number>()
  const finishing = new Set<string>()
  const listeners = new Set<FinishListener>()
  let ticker: ReturnType<typeof setInterval> | undefined

  const active = computed(() =>
    Object.values(runs.value)
      .filter((r) => isActiveStatus(r.status))
      .sort((a, b) => b.startedAt - a.startedAt),
  )
  /** 상단 바 pill 대상: 가장 최근에 시작한 진행 중 실행 */
  const primary = computed<LiveRun | null>(() => active.value[0] ?? null)

  function elapsedOf(runId: string): number | null {
    const r = runs.value[runId]
    if (!r) return null
    if (!isActiveStatus(r.status)) return r.elapsedMs
    return r.elapsedMs + Math.max(0, now.value - r.anchorAt)
  }

  function ensureTicker(): void {
    if (ticker !== undefined) return
    ticker = setInterval(() => {
      now.value = Date.now()
      if (active.value.length === 0) {
        clearInterval(ticker)
        ticker = undefined
      }
    }, TICK_MS)
  }

  function initialElapsed(run: RunState): number {
    if (typeof run.elapsed_ms === 'number') return run.elapsed_ms
    const created = Date.parse(run.created_at)
    return Number.isNaN(created) ? 0 : Math.max(0, Date.now() - created)
  }

  /** 진행 중 실행을 추적 대상에 올리고 스트림을 연다. 이미 추적 중이면 무시. */
  function track(run: RunState): void {
    if (!isActiveStatus(run.status)) return
    const id = run.run_id
    if (runs.value[id]) return
    runs.value[id] = {
      runId: id,
      title: run.title,
      parentRunId: run.parent_run_id,
      status: run.status,
      elapsedMs: initialElapsed(run),
      anchorAt: Date.now(),
      current: null,
      steps: run.steps,
      retryLoops: run.retry_loops ?? [],
      startedAt: Date.now(),
    }
    ensureTicker()
    openStream(id)
  }

  /** POST /api/runs 직후: RunState를 받아 추적을 시작한다. */
  async function trackById(runId: string): Promise<void> {
    if (runs.value[runId]) return
    try {
      const run = await api.run(runId)
      track(run)
    } catch {
      /* 화면에서 다시 조회하며 오류를 보여 준다 */
    }
  }

  function applyPayload(p: StreamPayload): void {
    const r = runs.value[p.run_id]
    if (!r) return
    r.status = p.status
    r.elapsedMs = p.elapsed_ms
    r.anchorAt = Date.now()
    r.current = p.current
    if (Array.isArray(p.steps) && p.steps.length > 0) r.steps = p.steps
    if (Array.isArray(p.retry_loops)) r.retryLoops = p.retry_loops
  }

  function openStream(runId: string): void {
    if (typeof EventSource === 'undefined') {
      startPolling(runId)
      return
    }
    const es = new EventSource(streamUrl(runId))
    sources.set(runId, es)
    errorCounts.set(runId, 0)

    for (const name of LISTEN_EVENTS) {
      es.addEventListener(name, (ev) => {
        errorCounts.set(runId, 0)
        let payload: StreamPayload
        try {
          payload = JSON.parse((ev as MessageEvent<string>).data) as StreamPayload
        } catch {
          return
        }
        applyPayload(payload)
        if (name === 'run_finished' || !isActiveStatus(payload.status)) void finish(runId)
      })
    }

    es.onerror = () => {
      const n = (errorCounts.get(runId) ?? 0) + 1
      errorCounts.set(runId, n)
      if (es.readyState === EventSource.CLOSED || n >= MAX_STREAM_ERRORS) {
        closeStream(runId)
        startPolling(runId)
      }
    }
  }

  function closeStream(runId: string): void {
    sources.get(runId)?.close()
    sources.delete(runId)
    errorCounts.delete(runId)
  }

  function startPolling(runId: string): void {
    if (pollers.has(runId)) return
    const tick = async () => {
      try {
        const run = await api.run(runId)
        const r = runs.value[runId]
        if (r) {
          r.status = run.status
          r.steps = run.steps
          r.retryLoops = run.retry_loops ?? []
          if (typeof run.elapsed_ms === 'number') {
            r.elapsedMs = run.elapsed_ms
            r.anchorAt = Date.now()
          }
        }
        if (!isActiveStatus(run.status)) void finish(runId, run)
      } catch {
        /* 다음 주기에 재시도 */
      }
    }
    pollers.set(runId, setInterval(tick, POLL_MS))
    void tick()
  }

  function stopPolling(runId: string): void {
    clearInterval(pollers.get(runId))
    pollers.delete(runId)
  }

  function toastFor(run: RunState): string {
    if (run.status === 'failed') return '분석을 완료하지 못했습니다'
    if (run.parent_run_id) return `재계산 완료 · 새 실행 ${run.run_id}`
    const v = run.validation
    if (run.status === 'partial') return '분석 일부 완료 · 결과를 확인하세요'
    if (!v) return '분석 완료'
    if (v.status === 'fail') return '분석 완료 · 검증 실패'
    const warns = v.issues.filter((i) => i.severity === 'warn').length
    return warns > 0 ? `분석 완료 · 검증 통과 (경고 ${warns}건)` : '분석 완료 · 검증 통과'
  }

  async function finish(runId: string, fetched?: RunState): Promise<void> {
    if (finishing.has(runId)) return
    finishing.add(runId)
    closeStream(runId)
    stopPolling(runId)

    let run: RunState | null = fetched ?? null
    if (!run) {
      try {
        run = await api.run(runId)
      } catch {
        run = null
      }
    }
    const r = runs.value[runId]
    if (r) {
      if (run) {
        r.status = run.status
        r.steps = run.steps
        r.retryLoops = run.retry_loops ?? r.retryLoops
        if (typeof run.elapsed_ms === 'number') r.elapsedMs = run.elapsed_ms
      } else if (isActiveStatus(r.status)) {
        r.status = 'failed'
      }
    }
    for (const fn of listeners) fn(run, runId)
    if (run) useUiStore().showToast(toastFor(run))
    void useHistoryStore().load()
    finishing.delete(runId)
  }

  function onFinish(fn: FinishListener): () => void {
    listeners.add(fn)
    return () => listeners.delete(fn)
  }

  return { runs, now, active, primary, elapsedOf, track, trackById, onFinish }
})
