import { describe, expect, it } from 'vitest'
import {
  EMPTY,
  MINUS,
  PNL_COLORS,
  formatAum,
  formatDate,
  formatDateTime,
  formatDelta,
  formatElapsed,
  formatEok,
  formatPct,
  formatPp,
  formatRange,
  formatShockInput,
  formatSigned,
  formatWeight,
  parseIso,
  parseShockInput,
  pnlColor,
  pnlTone,
  roundTo,
} from '../format'

describe('부호 표기', () => {
  it('음수는 유니코드 마이너스 U+2212를 쓴다', () => {
    const s = formatPct(-3.8)
    expect(s).toBe('−3.8%')
    expect(s.includes('-')).toBe(false)
    expect(MINUS.codePointAt(0)).toBe(0x2212)
  })

  it('양수는 +, 0은 부호 없음', () => {
    expect(formatPct(1.3)).toBe('+1.3%')
    expect(formatPct(0)).toBe('0.0%')
  })

  it('반올림 후 0이면 부호를 붙이지 않는다 (−0.0% 금지)', () => {
    expect(formatPct(-0.04)).toBe('0.0%')
    expect(formatPct(0.04)).toBe('0.0%')
    expect(formatPp(-0.004)).toBe('0.00%p')
    expect(roundTo(-0.04, 1)).toBe(0)
    expect(Object.is(roundTo(-0.04, 1), -0)).toBe(false)
  })

  it('자릿수를 지정할 수 있다', () => {
    expect(formatPp(-1.55)).toBe(`${MINUS}1.55%p`)
    expect(formatSigned(-0.15, { digits: 2 })).toBe(`${MINUS}0.15`)
    expect(formatSigned(5, { digits: 1, plus: false })).toBe('5.0')
  })

  it('값이 없거나 유한하지 않으면 대시', () => {
    expect(formatPct(null)).toBe(EMPTY)
    expect(formatPct(undefined)).toBe(EMPTY)
    expect(formatPct(Number.NaN)).toBe(EMPTY)
    expect(formatRange(null, 1)).toBe(EMPTY)
  })
})

describe('손익 색상 (국내식)', () => {
  it('이익은 빨강, 손실은 파랑', () => {
    expect(pnlColor(2.1)).toBe('#D23F31')
    expect(pnlColor(-3.8)).toBe('#1E5BD8')
    expect(PNL_COLORS.gain).toBe('#D23F31')
    expect(PNL_COLORS.loss).toBe('#1E5BD8')
  })

  it('0은 중립 회색, 값 없음은 연회색', () => {
    expect(pnlTone(0)).toBe('flat')
    expect(pnlColor(0)).toBe('#4A5363')
    expect(pnlTone(null)).toBe('none')
    expect(pnlColor(undefined)).toBe('#7A8394')
  })

  it('표시 자릿수를 주면 반올림 값 기준으로 색을 정한다', () => {
    expect(pnlTone(-0.04, 1)).toBe('flat')
    expect(pnlTone(-0.05, 1)).toBe('loss')
    expect(pnlTone(-0.04)).toBe('loss')
  })
})

describe('금액·범위·비중', () => {
  it('억 원 금액에 천 단위 쉼표', () => {
    expect(formatEok(-1240)).toBe(`${MINUS}1,240억 원`)
    expect(formatEok(310)).toBe('+310억 원')
    expect(formatEok(0)).toBe('0억 원')
  })

  it('추정 범위', () => {
    expect(formatRange(-5.1, -2.6)).toBe(`${MINUS}5.1% ~ ${MINUS}2.6%`)
    expect(formatRange(-1.2, 0.4)).toBe(`${MINUS}1.2% ~ +0.4%`)
  })

  it('운용자산 조·억 표기', () => {
    expect(formatAum(32300)).toBe('3조 2,300억 원')
    expect(formatAum(21000)).toBe('2조 1,000억 원')
    expect(formatAum(20000)).toBe('2조 원')
    expect(formatAum(850)).toBe('850억 원')
  })

  it('비중은 부호 없이', () => {
    expect(formatWeight(14)).toBe('14.0%')
    expect(formatWeight(6.25)).toBe('6.3%')
  })

  it('전일 대비 증감', () => {
    expect(formatDelta(1)).toBe('+1')
    expect(formatDelta(-2)).toBe(`${MINUS}2`)
    expect(formatDelta(0)).toBe('0')
  })
})

describe('충격값 입력', () => {
  it('단위별 자릿수로 초기 문자열을 만든다', () => {
    expect(formatShockInput(5, '%')).toBe('+5.0')
    expect(formatShockInput(-12, '%')).toBe(`${MINUS}12.0`)
    expect(formatShockInput(-0.15, '%p')).toBe(`${MINUS}0.15`)
  })

  it('유니코드 마이너스·하이픈·플러스·공백을 허용한다', () => {
    expect(parseShockInput(`${MINUS}12.0`)).toBe(-12)
    expect(parseShockInput('-12')).toBe(-12)
    expect(parseShockInput('+7')).toBe(7)
    expect(parseShockInput('  7.5 ')).toBe(7.5)
    expect(parseShockInput('.5')).toBe(0.5)
    expect(parseShockInput('3.')).toBe(3)
  })

  it('숫자가 아니면 null', () => {
    expect(parseShockInput('')).toBeNull()
    expect(parseShockInput('-')).toBeNull()
    expect(parseShockInput('abc')).toBeNull()
    expect(parseShockInput('1e3')).toBeNull()
    expect(parseShockInput('5%')).toBeNull()
    expect(parseShockInput('1,000')).toBeNull()
    expect(parseShockInput('--1')).toBeNull()
  })
})

describe('시간·날짜', () => {
  it('경과 시간은 0.1초 단위 내림', () => {
    expect(formatElapsed(14000)).toBe('14.0s')
    expect(formatElapsed(4249)).toBe('4.2s')
    expect(formatElapsed(0)).toBe('0.0s')
    expect(formatElapsed(null)).toBe('')
  })

  it('날짜 표기', () => {
    expect(formatDate('2026-10-14')).toBe('2026-10-14')
    expect(formatDateTime(null)).toBe(EMPTY)
    expect(formatDate(null)).toBe(EMPTY)
  })

  it('일시는 한국 시간(Asia/Seoul) 기준, 시간대 없는 ISO는 UTC로 해석', () => {
    expect(formatDateTime('2026-10-14T09:31:00')).toBe('2026-10-14 18:31')
    expect(formatDateTime('2026-10-14T09:31:00.123456')).toBe('2026-10-14 18:31')
    expect(formatDateTime('2026-10-14T09:31:00Z')).toBe('2026-10-14 18:31')
    expect(formatDateTime('2026-10-14T18:31:00+09:00')).toBe('2026-10-14 18:31')
    // UTC 늦은 밤 → KST 다음 날
    expect(formatDateTime('2026-10-14T16:05:00')).toBe('2026-10-15 01:05')
    expect(formatDate('2026-10-14T16:05:00')).toBe('2026-10-15')
    expect(formatDate('2026-10-14T16:05:00+09:00')).toBe('2026-10-14')
  })

  it('파싱할 수 없는 일시는 입력을 그대로', () => {
    expect(formatDateTime('어제')).toBe('어제')
    expect(formatDate('어제')).toBe('어제')
  })

  it('parseIso: 시간대 없는 ISO = UTC, 날짜만 = UTC 자정', () => {
    expect(parseIso('2026-10-14T08:29:10')?.toISOString()).toBe('2026-10-14T08:29:10.000Z')
    expect(parseIso('2026-10-14T17:29:10+09:00')?.toISOString()).toBe('2026-10-14T08:29:10.000Z')
    expect(parseIso('2026-10-14')?.toISOString()).toBe('2026-10-14T00:00:00.000Z')
    expect(parseIso(null)).toBeNull()
    expect(parseIso('')).toBeNull()
  })
})
