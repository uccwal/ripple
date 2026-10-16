/**
 * docs/API_CONTRACT.md 의 응답 형태를 그대로 옮긴 타입.
 * 단위: 손익·수익률 %, 기여도 %p, 금액 억 원, 날짜 YYYY-MM-DD / ISO 8601.
 */

export type CountryCode = 'US' | 'KR' | 'EU' | 'CN'
export type EventType = 'tariff' | 'rate' | 'regulation'
export type Entry = 'event' | 'scenario'
export type Confidence = 'high' | 'mid' | 'low'
export type Direction = '+' | '-'
export type Layer = 'policy' | 'industry' | 'macro' | 'asset'
export type LlmMode = 'anthropic' | 'offline'
export type RunStatus = 'queued' | 'running' | 'done' | 'partial' | 'failed'
export type StepStatus = 'wait' | 'running' | 'done' | 'retry' | 'failed' | 'skip'
export type ValidationStatus = 'pass' | 'warn' | 'fail'
export type ShockUnit = '%' | '%p'
/** 수집 시 Claude가 판정한 포트폴리오 관련성 (offline 모드·예시 이벤트는 null) */
export type Relevance = 'high' | 'mid' | 'low'

/* ---------- /api/meta ---------- */

export interface Meta {
  service: string
  engine_version: string
  llm_mode: LlmMode
  model_default: string
  last_collected_at: string | null
  today_event_count: number
  today_event_delta: number
  events_by_source: { source: string; count: number }[]
  synthetic_data: boolean
  database: DatabaseInfo
  radar: Radar
}

/** 대시보드 상단 레이더 (최근 7일) */
export interface Radar {
  events_7d: number
  events_7d_high: number
  events_7d_kr: number
  runs_7d: number
  auto_runs_7d: number
  backtest: BacktestStats
  quality_issues: string[]
  synthetic_remaining: string[]
}

export interface BacktestStats {
  n_cases: number
  n_judged: number
  /** 0~1 */
  direction_hit_rate: number | null
  /** %p */
  mean_abs_error: number | null
  /** 0~1 */
  factor_hit_rate: number | null
}

export interface BacktestCase {
  run_id: string
  title: string
  portfolio_id: string
  announced_at: string | null
  estimate_pnl: number | null
  actual_pnl: number | null
  direction_hit: boolean | null
  abs_error: number | null
  factor_hit_rate: number | null
}

export interface BacktestSummary extends BacktestStats {
  cases: BacktestCase[]
}

/** DB 종류. sqlite 는 컨테이너 안 파일이라 재배포 때 초기화된다 */
export interface DatabaseInfo {
  dialect: string
  persistent: boolean
}

/* ---------- /api/events ---------- */

export interface EventSummary {
  event_id: string
  country: CountryCode
  country_name: string
  type: EventType
  type_name: string
  title: string
  summary: string
  targets: string[]
  value: number | null
  value_text: string
  announced_at: string
  source: string
  source_url: string | null
  is_demo: boolean
  /** 원문 제목 (외국어 이벤트를 한국어로 구조화한 경우). 한국어·예시 이벤트는 null */
  title_orig: string | null
  relevance: Relevance | null
  last_run: EventLastRun | null
}

/** 이벤트의 최근 분석 (자동 사전분석 포함) */
export interface EventLastRun {
  run_id: string
  status: RunStatus
  auto: boolean
  portfolio_id: string
  portfolio_pnl: number | null
  pnl_amount: number | null
  validation_status: ValidationStatus | null
  /** 사후 검증 — 발표 후 실제 손익 (데이터 없으면 null) */
  actual_pnl: number | null
  direction_hit: boolean | null
  created_at: string | null
}

export interface EventDetail extends EventSummary {
  raw_text: string
  collected_at: string
}

export interface EventQuery {
  country?: CountryCode
  type?: EventType
  days?: 7 | 30 | 90
  /** high: 높음만 · mid: 높음·중간 (미평가·예시 이벤트는 항상 포함) · 생략: 전체 */
  relevance?: 'high' | 'mid'
  /** 기본 200 */
  limit?: number
}

/* ---------- /api/portfolios ---------- */

export interface PortfolioSummary {
  portfolio_id: string
  name: string
  base_currency: string
  description: string
  aum: number
  holdings_count: number
}

export interface Holding {
  asset_id: string
  name: string
  asset_class: string
  currency: string
  sector: string
  /** % (합계 100) */
  weight: number
}

export interface PortfolioDetail extends Omit<PortfolioSummary, 'holdings_count'> {
  holdings: Holding[]
}

/* ---------- /api/runs ---------- */

export interface CreateRunRequest {
  entry: Entry
  event_id?: string
  scenario_text?: string
  portfolio_id: string
  horizon_days?: number
}

export interface RunIdResponse {
  run_id: string
}

export interface Step {
  idx: number
  agent: string
  desc: string
  status: StepStatus
  attempt: number
  elapsed_ms: number | null
  note: string | null
  input_summary: string | null
  output_summary: string | null
  model: string | null
  tokens: string | null
}

export interface RetryLoop {
  from_idx: number
  to_idx: number
}

export interface RunEvent {
  event_id: string
  country: CountryCode
  type: EventType
  title: string
  targets: string[]
  value: number | null
  value_text: string
  announced_at: string
  source: string
  source_url: string | null
}

export interface PathStep {
  from: string
  to: string
  direction: Direction
  confidence: Confidence
  evidence: string[]
}

export interface ImpactPath {
  path_id: string
  excluded: boolean
  reason: string | null
  steps: PathStep[]
}

export interface Evidence {
  id: string
  text: string
  source: string
  collected_at: string
}

export interface GraphNode {
  id: string
  label: string
  layer: Layer
  confidence: Confidence
  factor_id: string | null
  direction_text: string
  evidence: Evidence[]
}

export interface GraphEdge {
  source: string
  target: string
  direction: Direction
  confidence: Confidence
}

export interface Graph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface Shock {
  variable: string
  name: string
  change: number
  unit: ShockUnit
  basis: string
  hist_max: number
  hist_pct: number
  over_hist: boolean
}

export interface Scenario {
  horizon_days: number
  shocks: Shock[]
}

export interface Regime {
  start: string
  end: string
  similarity: number
  tag: string
  pnl: number
  factor_changes: Record<string, number>
}

export interface AssetResult {
  asset_id: string
  name: string
  weight: number
  ret: number
  contribution: number
  currency: string
  sector: string
  asset_class: string
}

export interface FactorContribution {
  factor_id: string
  name: string
  beta: number
  se: number
  shock: number
  unit: ShockUnit
  contribution: number
  share: number
}

export interface Hedge {
  rule_id: string
  title: string
  why: string
  rule: string
  key: string
}

export interface RunResult {
  portfolio_pnl: number
  pnl_amount: number
  aum: number
  range: { low: number; high: number }
  by_asset: AssetResult[]
  top_contributors: string[]
  factor_contrib: FactorContribution[]
  regime_estimate: { median: number; low: number; high: number; n: number } | null
  hedges: Hedge[]
  calc_log_id: string
  /** 사후 검증 — 발표일이 과거인 이벤트 분석에만 (시나리오 입력·미래 이벤트는 null) */
  actual: ActualOutcome | null
  /** 같은 충격값을 모든 모델 포트폴리오에 적용. 첫 행이 현재 포트폴리오 */
  cross_portfolio: CrossPortfolioRow[]
}

export interface ActualFactor {
  name: string
  unit: ShockUnit
  shock: number | null
  actual: number
  hit: boolean | null
}

export interface ActualOutcome {
  start: string
  end: string
  days: number
  horizon: number
  complete: boolean
  factors: Record<string, ActualFactor>
  factor_hit_rate: number | null
  factors_judged: number
  by_asset: Record<string, number | null>
  portfolio_pnl: number | null
  estimate_pnl: number | null
  direction_hit: boolean | null
  abs_error: number | null
}

export interface CrossPortfolioRow {
  portfolio_id: string
  name: string
  aum: number
  pnl: number | null
  amount: number | null
  range: { low: number; high: number } | null
  worst_asset: string | null
  worst_contribution: number | null
  current: boolean
  error: string | null
}

export interface ValidationIssue {
  code: string
  severity: 'warn' | 'error'
  agent: string
  message: string
}

export interface Validation {
  passed: boolean
  status: ValidationStatus
  rules_total: number
  rules_passed: number
  issues: ValidationIssue[]
}

export interface Citation {
  n: number
  name: string
  collected_at: string
  url: string | null
}

export interface Report {
  markdown: string
  citations: Citation[]
}

export interface RunState {
  run_id: string
  parent_run_id: string | null
  entry: Entry
  status: RunStatus
  error: string | null
  /** 수집 직후 자동 사전분석으로 만든 실행 */
  auto: boolean
  title: string
  input_text: string | null
  portfolio: { portfolio_id: string; name: string; aum: number }
  horizon_days: number
  as_of: string
  created_at: string
  finished_at: string | null
  elapsed_ms: number | null
  llm_mode: LlmMode
  synthetic_data: boolean
  event: RunEvent | null
  impact_paths: ImpactPath[]
  graph: Graph | null
  scenario: Scenario | null
  regimes: Regime[]
  result: RunResult | null
  validation: Validation | null
  report: Report | null
  steps: Step[]
  /** Validator 반려 루프 (타임라인 화살표). 반려가 없으면 빈 배열 또는 생략. */
  retry_loops?: RetryLoop[]
}

export interface RunListItem {
  run_id: string
  created_at: string
  entry: Entry
  title: string
  portfolio_name: string
  portfolio_pnl: number | null
  validation_status: ValidationStatus | null
  status: RunStatus
  auto: boolean
  actual_pnl: number | null
  direction_hit: boolean | null
}

export interface ScenarioPatchRequest {
  shocks: { variable: string; change: number }[]
}

/* ---------- SSE /api/runs/{id}/stream ---------- */

export type StreamEventName = 'step_started' | 'step_finished' | 'step_retry' | 'step_failed' | 'run_finished'

export const STREAM_EVENTS: readonly StreamEventName[] = [
  'step_started',
  'step_finished',
  'step_retry',
  'step_failed',
  'run_finished',
]

export interface StreamPayload {
  run_id: string
  status: RunStatus
  elapsed_ms: number
  current: string | null
  step: Step | null
  steps: Step[]
  retry_loops: RetryLoop[]
}

/* ---------- /api/runs/{id}/calc-log ---------- */

export interface CalcCell {
  v: string
  /** 있으면 손익색 + 700 */
  num?: number
}

export interface CalcEntry {
  title: string
  value: number | null
  value_text: string
  sub: string | null
  formula: string
  columns: string[]
  rows: CalcCell[][]
  note: string | null
}

export interface CalcSource {
  name: string
  collected_at: string
  synthetic: boolean
}

export interface CalcLog {
  calc_id: string
  run_id: string
  code_hash: string
  engine_version: string
  created_at: string
  sources: CalcSource[]
  entries: Record<string, CalcEntry>
  inputs: Record<string, unknown>
  outputs: Record<string, unknown>
}

/* ---------- /api/data/status (S7 데이터 관리) ---------- */

export type SeriesRole = 'factor' | 'asset' | 'other'
/** 시계열 품질: ok · stale(최종 관측 지연) · gappy(결측 많음) · synthetic(합성) · empty(값 없음) */
export type SeriesQuality = 'ok' | 'stale' | 'gappy' | 'synthetic' | 'empty'
export type CollectReportStatus = 'ok' | 'skipped' | 'error'

export interface SeriesStatus {
  series_id: string
  name: string
  source: string
  unit: string
  license: string | null
  source_url: string | null
  count: number
  first_date: string | null
  last_date: string | null
  /** naive UTC ISO (DB 컬럼 기준) */
  collected_at: string | null
  synthetic: boolean
  /** 팩터 카탈로그 또는 포트폴리오 가격 결정에 쓰이는 시리즈 */
  in_use: boolean
  role: SeriesRole
  factor_name: string | null
  /** 최종 관측일 이후 지난 영업일 수 (값이 없으면 null) */
  stale_bdays: number | null
  /** 기간 내 영업일 대비 관측 비율 0~1 (값이 없으면 null) */
  coverage: number | null
  quality: SeriesQuality
}

export interface EventSourceStatus {
  source: string
  is_demo: boolean
  count: number
  first_date: string | null
  last_date: string | null
}

export interface CollectorStatus {
  name: string
  description: string
  /** 필요한 환경 변수 이름. 키가 필요 없으면 null */
  required_key: string | null
  key_present: boolean
}

export interface CollectReport {
  collector: string
  status: CollectReportStatus
  message: string
  counts: Record<string, number>
}

export interface CollectState {
  running: boolean
  started_at: string | null
  finished_at: string | null
  /** 시간대 포함 ISO (UTC) */
  next_scheduled_at: string | null
  error: string | null
  reports: CollectReport[]
}

export interface DataStatus {
  llm_mode: LlmMode
  model_default: string
  model_impact_mapper: string
  /** 아직 합성 데이터로 계산 중인(사용 중인) 시리즈 id */
  synthetic_remaining: string[]
  /** 사용 중인데 지연·결측·빈 값인 시리즈 id */
  quality_issues: string[]
  series: SeriesStatus[]
  events: EventSourceStatus[]
  collectors: CollectorStatus[]
  collect: CollectState
  admin_enabled: boolean
  daily_hour_utc: number | null
  database: DatabaseInfo
}

/* ---------- POST /api/admin/collect ---------- */

export interface CollectRequest {
  /** YYYY-MM-DD */
  since?: string
  only?: string[]
}

export interface CollectStartResponse {
  started: boolean
  since: string | null
  only: string[] | null
}
