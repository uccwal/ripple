/**
 * 수치 표기 규칙 (docs/design/README.md 전역 규칙)
 * - 음수 부호는 유니코드 마이너스 U+2212, 양수는 '+', 0은 부호 없음.
 * - 부호·색은 "화면에 보이는 반올림 값" 기준으로 정한다. (−0.0% 같은 표기를 만들지 않는다)
 * - 손익 색상은 국내식: 이익 빨강 #D23F31, 손실 파랑 #1E5BD8, 0 #4A5363, 값 없음 #7A8394.
 */

export const MINUS = '−'
export const EMPTY = '—'

export const PNL_COLORS = {
  gain: '#D23F31',
  loss: '#1E5BD8',
  flat: '#4A5363',
  none: '#7A8394',
} as const

export type PnlTone = keyof typeof PNL_COLORS

/** 표시 자릿수로 반올림한 값. -0은 0으로 정규화한다. */
export function roundTo(value: number, digits: number): number {
  const r = Number(value.toFixed(digits))
  return Object.is(r, -0) ? 0 : r
}

function isNum(v: number | null | undefined): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/** 손익 톤. `digits`를 주면 그 자릿수로 반올림한 값 기준으로 판단한다. */
export function pnlTone(value: number | null | undefined, digits?: number): PnlTone {
  if (!isNum(value)) return 'none'
  const v = digits === undefined ? value : roundTo(value, digits)
  if (v > 0) return 'gain'
  if (v < 0) return 'loss'
  return 'flat'
}

export function pnlColor(value: number | null | undefined, digits?: number): string {
  return PNL_COLORS[pnlTone(value, digits)]
}

export interface SignedOptions {
  /** 소수 자릿수 (기본 1) */
  digits?: number
  /** 양수에 '+'를 붙인다 (기본 true) */
  plus?: boolean
  /** 천 단위 구분 쉼표 (기본 false) */
  grouping?: boolean
}

/** 부호 있는 숫자 문자열: +5.0 / −3.8 / 0.0 */
export function formatSigned(value: number, { digits = 1, plus = true, grouping = false }: SignedOptions = {}): string {
  const r = roundTo(value, digits)
  const abs = Math.abs(r)
  const body = grouping
    ? abs.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
    : abs.toFixed(digits)
  if (r > 0) return (plus ? '+' : '') + body
  if (r < 0) return MINUS + body
  return body
}

/** 단위가 붙은 손익 표기. 값이 없으면 '—'. */
export function formatWithUnit(value: number | null | undefined, unit: string, opts: SignedOptions = {}): string {
  if (!isNum(value)) return EMPTY
  return formatSigned(value, opts) + unit
}

/** −3.8% */
export function formatPct(value: number | null | undefined, digits = 1): string {
  return formatWithUnit(value, '%', { digits })
}

/** −1.55%p */
export function formatPp(value: number | null | undefined, digits = 2): string {
  return formatWithUnit(value, '%p', { digits })
}

/** 억 원 금액: −1,240억 원 */
export function formatEok(value: number | null | undefined): string {
  return formatWithUnit(value, '억 원', { digits: 0, grouping: true })
}

/** 추정 범위: −5.1% ~ −2.6% */
export function formatRange(low: number | null | undefined, high: number | null | undefined, digits = 1): string {
  if (!isNum(low) || !isNum(high)) return EMPTY
  return `${formatPct(low, digits)} ~ ${formatPct(high, digits)}`
}

/** 충격값 단위별 기본 자릿수: %p(금리)는 2자리, %는 1자리 */
export function shockDigits(unit: string): number {
  return unit === '%p' ? 2 : 1
}

/** 충격값 입력칸 초기 문자열: +5.0 / −12.0 / −0.15 */
export function formatShockInput(value: number, unit: string): string {
  return formatSigned(value, { digits: shockDigits(unit) })
}

const SHOCK_PATTERN = /^[+\-−]?(?:\d+(?:\.\d*)?|\.\d+)$/

/**
 * 충격값 입력 파싱. 유니코드 마이너스·플러스 부호·앞뒤 공백을 허용한다.
 * 숫자가 아니면 null.
 */
export function parseShockInput(text: string): number | null {
  const s = text.trim().replace(/\s+/g, '')
  if (!SHOCK_PATTERN.test(s)) return null
  const n = Number(s.replace(MINUS, '-').replace('+', ''))
  return Number.isFinite(n) ? n : null
}

/** 부호 있는 정수 (전일 대비 +1 / −2 / 0) */
export function formatDelta(value: number | null | undefined): string {
  if (!isNum(value)) return EMPTY
  return formatSigned(value, { digits: 0 })
}

/** 억 원 단위 운용자산: 32300 → '3조 2,300억 원' */
export function formatAum(eok: number | null | undefined): string {
  if (!isNum(eok)) return EMPTY
  const total = Math.round(eok)
  const jo = Math.floor(Math.abs(total) / 10000)
  const rest = Math.abs(total) % 10000
  const sign = total < 0 ? MINUS : ''
  const parts: string[] = []
  if (jo > 0) parts.push(`${jo.toLocaleString('en-US')}조`)
  if (rest > 0 || jo === 0) parts.push(`${rest.toLocaleString('en-US')}억`)
  return `${sign}${parts.join(' ')} 원`
}

/** 비중: 14 → '14.0%' (부호 없음) */
export function formatWeight(value: number | null | undefined, digits = 1): string {
  if (!isNum(value)) return EMPTY
  return `${roundTo(value, digits).toFixed(digits)}%`
}

/** 경과 시간: 14000 → '14.0s' */
export function formatElapsed(ms: number | null | undefined): string {
  if (!isNum(ms) || ms < 0) return ''
  return `${(Math.floor(ms / 100) / 10).toFixed(1)}s`
}

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/**
 * ISO 일시 → 'YYYY-MM-DD HH:mm' (브라우저 로컬 시각).
 * 시간대가 없는 ISO 문자열은 로컬 시각으로 해석된다.
 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** ISO 일시/날짜 → 'YYYY-MM-DD' */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return EMPTY
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
