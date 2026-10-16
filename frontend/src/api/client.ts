import type {
  BacktestSummary,
  CalcLog,
  CollectRequest,
  CollectStartResponse,
  CreateRunRequest,
  DataStatus,
  EventDetail,
  EventQuery,
  EventSummary,
  Meta,
  PortfolioDetail,
  PortfolioSummary,
  RunIdResponse,
  RunListItem,
  RunState,
  ScenarioPatchRequest,
} from './types'

/**
 * API 베이스. 같은 서버에서 서빙하면 '/api'. 프론트엔드를 정적 호스팅(GitHub Pages 등)에 따로 올릴 때는
 * 빌드 시 VITE_API_BASE=https://<api-host> 를 주면 '<api-host>/api' 로 요청한다.
 */
const apiHost = (import.meta.env.VITE_API_BASE ?? '').replace(/\/+$/, '')
export const API_BASE = `${apiHost}/api`

/** 백엔드 오류. `status`가 0이면 네트워크 단절(백엔드 미기동 등). */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string | null

  constructor(status: number, message: string, detail: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function describeStatus(status: number): string {
  if (status === 0) return '서버에 연결할 수 없습니다. 백엔드(:8000)가 실행 중인지 확인하세요.'
  if (status === 403) return '권한이 없습니다.'
  if (status === 404) return '요청한 항목을 찾을 수 없습니다.'
  if (status === 409) return '이미 진행 중인 작업이 있습니다.'
  if (status === 422 || status === 400) return '요청 형식이 올바르지 않습니다.'
  if (status >= 500) return '서버 오류가 발생했습니다.'
  return `요청에 실패했습니다 (HTTP ${status}).`
}

async function readDetail(res: Response): Promise<string | null> {
  try {
    const body: unknown = await res.json()
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      if (typeof detail === 'string') return detail
      return JSON.stringify(detail)
    }
  } catch {
    /* 본문이 JSON이 아니면 무시 */
  }
  return null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, describeStatus(0))
  }
  if (!res.ok) {
    const detail = await readDetail(res)
    throw new ApiError(res.status, describeStatus(res.status), detail)
  }
  return (await res.json()) as T
}

function query(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

const enc = encodeURIComponent

export const api = {
  meta: (signal?: AbortSignal) => request<Meta>('/meta', { signal }),

  events: (params: EventQuery = {}, signal?: AbortSignal) =>
    request<EventSummary[]>(`/events${query({ ...params })}`, { signal }),
  event: (id: string) => request<EventDetail>(`/events/${enc(id)}`),

  portfolios: () => request<PortfolioSummary[]>('/portfolios'),
  portfolio: (id: string) => request<PortfolioDetail>(`/portfolios/${enc(id)}`),

  runs: () => request<RunListItem[]>('/runs'),
  run: (id: string, signal?: AbortSignal) => request<RunState>(`/runs/${enc(id)}`, { signal }),
  createRun: (body: CreateRunRequest) =>
    request<RunIdResponse>('/runs', { method: 'POST', body: JSON.stringify(body) }),
  patchScenario: (id: string, body: ScenarioPatchRequest) =>
    request<RunIdResponse>(`/runs/${enc(id)}/scenario`, { method: 'PATCH', body: JSON.stringify(body) }),
  calcLog: (id: string) => request<CalcLog>(`/runs/${enc(id)}/calc-log`),
  /** 사후 검증 집계 (발표 후 분석 기간이 지난 이벤트 분석) */
  backtest: (limit = 100, signal?: AbortSignal) => request<BacktestSummary>(`/backtest${query({ limit })}`, { signal }),

  /** S7 데이터 관리 — 토큰 불필요 */
  getDataStatus: (signal?: AbortSignal) => request<DataStatus>('/data/status', { signal }),
  /** 수집 시작 (202). 403 토큰 오류 · 409 이미 진행 중 · 404 관리용 API 비활성 */
  startCollect: (token: string, body: CollectRequest = {}) =>
    request<CollectStartResponse>('/admin/collect', {
      method: 'POST',
      body: JSON.stringify(body),
      headers: { 'X-Admin-Token': token },
    }),
}

/** SSE 스트림 URL (EventSource용) */
export const streamUrl = (runId: string) => `${API_BASE}/runs/${enc(runId)}/stream`

/** 보고서 URL. md = 파일 다운로드, html = 인쇄용 문서(브라우저 인쇄 → PDF) */
export const reportUrl = (runId: string, format: 'md' | 'html') =>
  `${API_BASE}/runs/${enc(runId)}/report${query({ format })}`

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail ? `${err.message} (${err.detail})` : err.message
  if (err instanceof Error) return err.message
  return '알 수 없는 오류가 발생했습니다.'
}
