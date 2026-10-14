import { describe, expect, it } from 'vitest'
import { EMPTY } from '../format'
import {
  formatDailyKst,
  formatDateRange,
  formatDuration,
  formatInt,
  formatKst,
  formatLocalDateTime,
  formatRelative,
  parseIso,
  summarizeCounts,
} from '../dataStatus'

const NOW = Date.UTC(2026, 9, 14, 9, 0, 0) // 2026-10-14T09:00:00Z

describe('parseIso — 시간대 없는 ISO는 UTC로 본다', () => {
  it('naive ISO → UTC', () => {
    expect(parseIso('2026-10-14T08:29:10')?.toISOString()).toBe('2026-10-14T08:29:10.000Z')
    expect(parseIso('2026-10-14T08:29:10.121416')?.getTime()).toBe(Date.UTC(2026, 9, 14, 8, 29, 10, 121))
  })
  it('시간대가 있으면 그대로', () => {
    expect(parseIso('2026-10-14T08:29:10Z')?.toISOString()).toBe('2026-10-14T08:29:10.000Z')
    expect(parseIso('2026-10-14T17:29:10+09:00')?.toISOString()).toBe('2026-10-14T08:29:10.000Z')
    expect(parseIso('2026-10-14T08:29:10+00:00')?.toISOString()).toBe('2026-10-14T08:29:10.000Z')
  })
  it('날짜만 있으면 UTC 자정, 빈 값·잘못된 값은 null', () => {
    expect(parseIso('2026-10-14')?.toISOString()).toBe('2026-10-14T00:00:00.000Z')
    expect(parseIso(null)).toBeNull()
    expect(parseIso('')).toBeNull()
    expect(parseIso('어제')).toBeNull()
  })
})

describe('formatRelative', () => {
  it('과거: 방금 · 분 · 시간 · 일 · 개월 · 년', () => {
    expect(formatRelative('2026-10-14T08:59:40', NOW)).toBe('방금 전')
    expect(formatRelative('2026-10-14T08:48:00', NOW)).toBe('12분 전')
    expect(formatRelative('2026-10-14T05:30:00', NOW)).toBe('3시간 전')
    expect(formatRelative('2026-10-12T09:00:00', NOW)).toBe('2일 전')
    expect(formatRelative('2026-08-01T09:00:00', NOW)).toBe('2개월 전')
    expect(formatRelative('2024-10-01T09:00:00', NOW)).toBe('2년 전')
  })
  it('미래는 …후', () => {
    expect(formatRelative('2026-10-14T09:00:30Z', NOW)).toBe('잠시 후')
    expect(formatRelative('2026-10-14T09:45:00Z', NOW)).toBe('45분 후')
    expect(formatRelative('2026-10-15T00:00:00+00:00', NOW)).toBe('15시간 후')
  })
  it('값이 없으면 대시', () => {
    expect(formatRelative(null, NOW)).toBe(EMPTY)
    expect(formatRelative(undefined, NOW)).toBe(EMPTY)
  })
})

describe('KST 표기', () => {
  it('UTC → KST (+9), 자정 넘김 포함', () => {
    expect(formatKst('2026-10-15T00:00:00+00:00')).toBe('2026-10-15 09:00 KST')
    expect(formatKst('2026-10-14T23:30:00Z')).toBe('2026-10-15 08:30 KST')
    expect(formatKst('2026-10-14T08:29:10')).toBe('2026-10-14 17:29 KST')
    expect(formatKst('2026-10-14T15:05:00Z', { suffix: false })).toBe('2026-10-15 00:05')
  })
  it('한 자리 시각도 두 자리로', () => {
    expect(formatKst('2026-10-13T16:07:00Z')).toBe('2026-10-14 01:07 KST')
  })
  it('없으면 대시', () => {
    expect(formatKst(null)).toBe(EMPTY)
  })
  it('매일 수집 시각 (UTC 시 → KST)', () => {
    expect(formatDailyKst(0)).toBe('매일 09:00 KST')
    expect(formatDailyKst(15)).toBe('매일 00:00 KST')
    expect(formatDailyKst(23)).toBe('매일 08:00 KST')
    expect(formatDailyKst(null)).toBeNull()
    expect(formatDailyKst(undefined)).toBeNull()
    expect(formatDailyKst(24)).toBeNull()
  })
})

describe('formatLocalDateTime', () => {
  it("'YYYY-MM-DD HH:mm' 형식, naive는 UTC 기준", () => {
    const s = formatLocalDateTime('2026-10-14T08:29:10')
    expect(s).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
    const d = new Date('2026-10-14T08:29:10Z')
    const pad = (n: number) => String(n).padStart(2, '0')
    expect(s).toBe(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`)
    expect(formatLocalDateTime(null)).toBe(EMPTY)
  })
})

describe('건수', () => {
  it('천 단위 쉼표', () => {
    expect(formatInt(3073)).toBe('3,073')
    expect(formatInt(0)).toBe('0')
    expect(formatInt(1_234_567)).toBe('1,234,567')
    expect(formatInt(null)).toBe(EMPTY)
    expect(formatInt(Number.NaN)).toBe(EMPTY)
  })
  it('수집 결과 요약', () => {
    expect(summarizeCounts({ KOSPI: 1662, KR_K200: 1662 })).toBe('KOSPI 1,662 · KR_K200 1,662')
    expect(summarizeCounts({ DGS10: 0 })).toBe('DGS10 0')
    expect(summarizeCounts({})).toBe('')
    expect(summarizeCounts(null)).toBe('')
  })
})

describe('기간 · 소요', () => {
  it('기간', () => {
    expect(formatDateRange('2015-01-02', '2026-10-13')).toBe('2015-01-02 ~ 2026-10-13')
    expect(formatDateRange('2025-04-03', '2025-04-03')).toBe('2025-04-03')
    expect(formatDateRange(null, '2026-10-13')).toBe('2026-10-13')
    expect(formatDateRange(null, null)).toBe(EMPTY)
  })
  it('소요 시간', () => {
    expect(formatDuration('2026-10-14T08:00:00', '2026-10-14T08:00:12')).toBe('12초')
    expect(formatDuration('2026-10-14T08:00:00', '2026-10-14T08:03:04')).toBe('3분 4초')
    expect(formatDuration('2026-10-14T08:00:00', '2026-10-14T08:02:00')).toBe('2분')
    expect(formatDuration('2026-10-14T08:00:00', null)).toBe('')
  })
})
