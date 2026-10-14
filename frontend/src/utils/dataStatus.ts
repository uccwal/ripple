/**
 * S7 데이터 관리 화면의 시각·건수 표기.
 * - 백엔드의 시각은 대부분 시간대가 없는 ISO(naive UTC, DB 컬럼 기준)다. 그대로 `new Date()`에 넣으면
 *   브라우저 로컬 시각으로 잘못 해석되므로 여기서는 시간대가 없으면 UTC로 본다.
 * - 예약 수집 시각은 한국 시간(Asia/Seoul)으로 표기한다.
 */
import { EMPTY } from './format'

const KST = 'Asia/Seoul'
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/
const HAS_TZ = /(?:Z|[+-]\d{2}:?\d{2})$/i

function pad(n: number | string): string {
  return String(n).padStart(2, '0')
}

/** ISO 문자열 → Date. 시간대가 없으면 UTC로 해석한다. 파싱 실패·빈 값은 null. */
export function parseIso(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const s = DATE_ONLY.test(iso) ? `${iso}T00:00:00Z` : HAS_TZ.test(iso) ? iso : `${iso}Z`
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

/**
 * 상대 시각: 방금 전 · 12분 전 · 3시간 전 · 2일 전 · 1개월 전 · 1년 전.
 * 미래 시각은 '…후'. 값이 없으면 '—'.
 */
export function formatRelative(iso: string | null | undefined, now: number = Date.now()): string {
  const d = parseIso(iso)
  if (!d) return EMPTY
  const diff = now - d.getTime()
  const abs = Math.abs(diff)
  const past = diff >= 0
  if (abs < 60_000) return past ? '방금 전' : '잠시 후'
  const suffix = past ? '전' : '후'
  const minutes = Math.floor(abs / 60_000)
  if (minutes < 60) return `${minutes}분 ${suffix}`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}시간 ${suffix}`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}일 ${suffix}`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}개월 ${suffix}`
  return `${Math.floor(days / 365)}년 ${suffix}`
}

function kstParts(d: Date): { y: string; mo: string; d: string; h: string; mi: string } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: KST,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(d)
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? ''
  return { y: get('year'), mo: get('month'), d: get('day'), h: pad(get('hour')), mi: get('minute') }
}

/** 한국 시간 표기: '2026-10-15 09:00 KST' */
export function formatKst(iso: string | null | undefined, { suffix = true }: { suffix?: boolean } = {}): string {
  const d = parseIso(iso)
  if (!d) return EMPTY
  const p = kstParts(d)
  return `${p.y}-${p.mo}-${p.d} ${p.h}:${p.mi}${suffix ? ' KST' : ''}`
}

/** 매일 자동 수집 시각(UTC 시) → '매일 09:00 KST'. 설정이 없으면 null. */
export function formatDailyKst(hourUtc: number | null | undefined): string | null {
  if (typeof hourUtc !== 'number' || !Number.isInteger(hourUtc) || hourUtc < 0 || hourUtc > 23) return null
  return `매일 ${pad((hourUtc + 9) % 24)}:00 KST`
}

/** 브라우저 로컬 시각 'YYYY-MM-DD HH:mm' (시간대 없는 ISO는 UTC로 해석) */
export function formatLocalDateTime(iso: string | null | undefined): string {
  const d = parseIso(iso)
  if (!d) return EMPTY
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 정수 건수: 3073 → '3,073'. 값이 없으면 '—'. */
export function formatInt(n: number | null | undefined): string {
  if (typeof n !== 'number' || !Number.isFinite(n)) return EMPTY
  return Math.round(n).toLocaleString('en-US')
}

/** 수집 결과 건수 요약: {KOSPI: 1662, KR_K200: 1662} → 'KOSPI 1,662 · KR_K200 1,662'. 비어 있으면 ''. */
export function summarizeCounts(counts: Record<string, number> | null | undefined): string {
  if (!counts) return ''
  return Object.entries(counts)
    .map(([k, v]) => `${k} ${formatInt(v)}`)
    .join(' · ')
}

/** 기간: '2015-01-02 ~ 2026-10-13'. 한쪽만 있으면 그 값만, 둘 다 없으면 '—'. */
export function formatDateRange(first: string | null | undefined, last: string | null | undefined): string {
  if (first && last) return first === last ? first : `${first} ~ ${last}`
  return first || last || EMPTY
}

/** 두 시각 사이의 소요: '12초' · '3분 4초'. 계산 불가면 ''. */
export function formatDuration(startIso: string | null | undefined, endIso: string | null | undefined): string {
  const a = parseIso(startIso)
  const b = parseIso(endIso)
  if (!a || !b) return ''
  const sec = Math.max(0, Math.round((b.getTime() - a.getTime()) / 1000))
  if (sec < 60) return `${sec}초`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return s ? `${m}분 ${s}초` : `${m}분`
}
