// tailwind.config.js → theme.extend 에 병합
module.exports = {
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
    micro: ['11px', '14px'], caption: ['12px', '16px'], small: ['13px', '20px'], body: ['14px', '21px'],
    heading: ['16px', '24px'], title: ['22px', '30px'], display: ['30px', '36px'],
  },
  borderRadius: { xs: '3px', sm: '4px', DEFAULT: '6px', card: '8px' },
  boxShadow: {
    focus: '0 0 0 3px rgba(22,38,74,0.12)',
    panel: '-8px 0 24px rgba(20,26,36,0.12)',
    toast: '0 6px 20px rgba(20,26,36,0.2)',
    paper: '0 2px 8px rgba(20,26,36,0.05)',
  },
  minWidth: { app: '1280px' },
  width: { 'run-panel': '300px', 'calc-panel': '420px' },
};
