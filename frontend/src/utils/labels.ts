import type {
  CollectReportStatus,
  Confidence,
  CountryCode,
  Entry,
  EventType,
  Layer,
  SeriesRole,
  StepStatus,
  ValidationStatus,
} from '@/api/types'

export const ENTRY_LABEL: Record<Entry, string> = {
  event: '정책 이벤트',
  scenario: '직접 입력 시나리오',
}

/** S1·S6 표의 짧은 입구 표기 */
export const ENTRY_SHORT: Record<Entry, string> = {
  event: '이벤트',
  scenario: '시나리오',
}

export const COUNTRY_LABEL: Record<CountryCode, string> = {
  US: '미국',
  KR: '한국',
  EU: 'EU',
  CN: '중국',
}

export const EVENT_TYPE_LABEL: Record<EventType, string> = {
  tariff: '관세',
  rate: '금리',
  regulation: '규제',
}

export const LAYER_LABEL: Record<Layer, string> = {
  policy: '정책',
  industry: '산업',
  macro: '거시 변수',
  asset: '자산군',
}

export const LAYERS: readonly Layer[] = ['policy', 'industry', 'macro', 'asset']

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: '확신도 높음',
  mid: '확신도 중간',
  low: '확신도 낮음',
}

/** 엣지 선 스타일 (README S3 탭① 표) */
export const EDGE_STYLE: Record<Confidence, { stroke: string; width: number; dash: string | null; labelColor: string }> = {
  high: { stroke: '#16264A', width: 2.5, dash: null, labelColor: '#16264A' },
  mid: { stroke: '#8C9AB8', width: 2, dash: null, labelColor: '#4A5363' },
  low: { stroke: '#A3AAB6', width: 1.5, dash: '5 4', labelColor: '#7A8394' },
}

/** 타임라인 상태 아이콘·라벨 (README S3 좌측 패널 표) */
export interface StepVisual {
  bg: string
  border: string
  glyph: string
  glyphColor: string
  label: string
  labelColor: string
  nameColor: string
}

export const STEP_VISUAL: Record<StepStatus, StepVisual> = {
  wait: { bg: '#F5F6F8', border: '#CDD2DA', glyph: '', glyphColor: '#A3AAB6', label: '대기', labelColor: '#7A8394', nameColor: '#7A8394' },
  running: { bg: '#EEF1F7', border: '#16264A', glyph: '', glyphColor: '#16264A', label: '실행 중', labelColor: '#16264A', nameColor: '#141A24' },
  done: { bg: '#16264A', border: '#16264A', glyph: '✓', glyphColor: '#FFFFFF', label: '완료', labelColor: '#1B7F4B', nameColor: '#141A24' },
  retry: { bg: '#FFF4D1', border: '#D9A92E', glyph: '↺', glyphColor: '#8A5E00', label: '반려 · 재시도', labelColor: '#8A5E00', nameColor: '#141A24' },
  failed: { bg: '#FDECEA', border: '#B42318', glyph: '!', glyphColor: '#B42318', label: '실패', labelColor: '#B42318', nameColor: '#141A24' },
  skip: { bg: '#FFFFFF', border: '#E3E6EB', glyph: '–', glyphColor: '#CDD2DA', label: '해당 없음', labelColor: '#A3AAB6', nameColor: '#A3AAB6' },
}

export const VALIDATION_BADGE: Record<ValidationStatus, { text: string; variant: 'pass' | 'warn' | 'fail' }> = {
  pass: { text: '✓ 통과', variant: 'pass' },
  warn: { text: '⚠ 경고', variant: 'warn' },
  fail: { text: '! 실패', variant: 'fail' },
}

export const PIPELINE: Record<Entry, string> = {
  event: 'Event Analyst → Impact Mapper → Scenario Builder → Regime Finder → Risk Engine → Validator → Report Writer',
  scenario: 'Scenario Builder → Regime Finder → Risk Engine → Validator → Report Writer',
}

/* ---------- S7 데이터 관리 ---------- */

/** 시계열 역할 배지 (입구 유형 배지와 같은 navy-50 스타일) */
export const SERIES_ROLE_LABEL: Record<SeriesRole, string> = {
  factor: '팩터',
  asset: '자산',
  other: '보조',
}

export const SYNTHETIC_SERIES_TIP = '데모용 합성 시계열 — 수집기가 실데이터로 교체합니다'

/** 수집기 실행 결과 배지 */
export const COLLECT_REPORT_BADGE: Record<CollectReportStatus, { text: string; variant: 'pass' | 'outline' | 'fail' }> = {
  ok: { text: '✓ 성공', variant: 'pass' },
  skipped: { text: '건너뜀', variant: 'outline' },
  error: { text: '! 오류', variant: 'fail' },
}

export const LLM_MODE_LABEL = {
  anthropic: 'Claude 연결',
  offline: 'offline 규칙 모드',
} as const
