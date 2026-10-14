import type { Config } from 'tailwindcss'

type ThemeExtend = NonNullable<NonNullable<Config['theme']>['extend']>

/**
 * docs/design/tailwind.tokens.js 의 theme.extend 조각을 그대로 옮긴 값.
 * 원본이 바뀌면 이 객체도 함께 맞춘다.
 */
const designTokens = {
  colors: {
    navy: { 50: '#EEF1F7', 300: '#6F84B5', 500: '#3B5185', 700: '#2A3F6E', 900: '#16264A' },
    bg: '#F5F6F8',
    surface: { DEFAULT: '#FFFFFF', sunken: '#F8F9FA' },
    line: { DEFAULT: '#E3E6EB', subtle: '#EEF0F3', strong: '#CDD2DA' },
    ink: { DEFAULT: '#141A24', 2: '#4A5363', 3: '#7A8394', 4: '#A3AAB6' },
    gain: { DEFAULT: '#D23F31', bg: '#FDEDEB' },
    loss: { DEFAULT: '#1E5BD8', bg: '#EAF0FD' },
    pass: { DEFAULT: '#1B7F4B', bg: '#E5F4EC' },
    warn: { DEFAULT: '#8A5E00', bg: '#FFF4D1', loop: '#D9A92E' },
    fail: { DEFAULT: '#B42318', bg: '#FDECEA' },
    conf: { high: '#16264A', mid: '#8C9AB8', low: '#A3AAB6' },
  },
  fontFamily: {
    sans: ['"Pretendard Variable"', 'Pretendard', '-apple-system', '"Apple SD Gothic Neo"', 'sans-serif'],
    mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
  },
  fontSize: {
    micro: ['11px', '14px'],
    caption: ['12px', '16px'],
    small: ['13px', '20px'],
    body: ['14px', '21px'],
    heading: ['16px', '24px'],
    title: ['22px', '30px'],
    display: ['30px', '36px'],
  } satisfies Record<string, [string, string]>,
  borderRadius: { xs: '3px', sm: '4px', DEFAULT: '6px', card: '8px' },
  boxShadow: {
    focus: '0 0 0 3px rgba(22,38,74,0.12)',
    panel: '-8px 0 24px rgba(20,26,36,0.12)',
    toast: '0 6px 20px rgba(20,26,36,0.2)',
    paper: '0 2px 8px rgba(20,26,36,0.05)',
  },
  minWidth: { app: '1280px' },
  width: { 'run-panel': '300px', 'calc-panel': '420px' },
} satisfies ThemeExtend

/**
 * 핸드오프 README 본문에만 등장하는 보조 색 (토큰 파일에는 없음).
 * 화면 코드에 hex를 흩뿌리지 않도록 이름을 붙여 둔다.
 */
const specColors = {
  navy: { 100: '#E4E9F2', 200: '#C9D1E3' }, // 확신도 중간 배지 배경 · 스피너 트랙
  surface: {
    selected: '#F8F9FC', // S2 선택된 입구 카드
    muted: '#F7F8FA', // 확신도 낮음 노드
    evidence: '#FAFBFC', // 근거 항목 카드
  },
  skel: { DEFAULT: '#EEF0F3', strong: '#E7EAEE', block: '#F0F2F5' },
  warn: { note: '#FFF8E3', row: '#FFFCF2' },
  fail: { line: '#F3C3BD' },
  ink: { report: '#2A3140' },
  scrim: 'rgba(20,26,36,0.28)',
}

export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      ...designTokens,
      colors: {
        ...designTokens.colors,
        navy: { ...designTokens.colors.navy, ...specColors.navy },
        surface: { ...designTokens.colors.surface, ...specColors.surface },
        skel: specColors.skel,
        warn: { ...designTokens.colors.warn, ...specColors.warn },
        fail: { ...designTokens.colors.fail, ...specColors.fail },
        ink: { ...designTokens.colors.ink, ...specColors.ink },
        scrim: specColors.scrim,
      },
      keyframes: { rpspin: { to: { transform: 'rotate(360deg)' } } },
      animation: { rpspin: 'rpspin 0.8s linear infinite' },
    },
  },
  plugins: [],
} satisfies Config
