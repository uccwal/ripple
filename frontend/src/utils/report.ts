import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { MINUS, PNL_COLORS } from './format'

/**
 * 보고서 Markdown → 안전한 HTML.
 *
 * 백엔드 Report Writer는 수치를 `<!--k:KEY-->표기<!--/k-->` 마커로 감싼다 (KEY = calc_log outputs 키).
 * 마커를 data-k 속성을 가진 span으로 바꾼 뒤 marked(GFM) → DOMPurify로 정리하고,
 * calc-log entries 키로 이어지는 수치는 클릭 가능한 버튼(data-calc-key)으로 장식한다.
 */

const MARKER = /<!--k:([^>]*?)-->([\s\S]*?)<!--\/k-->/g

/** outputs 키 → S5 패널 entries 키. 연결할 항목이 없으면 null. */
export function calcKeyFor(outputKey: string): string | null {
  const base = outputKey.split('.')[0] ?? ''
  if (base === 'pnl' || base === 'amt' || base === 'range' || base === 'model' || base === 'reg') return base
  if (/^(h|fc|f):[A-Za-z0-9_-]+$/.test(base)) return base
  return null
}

/** 손익색을 입힐 수치인가 (충격값·범위·비중·유사도·비율은 본문색) */
export function isPnlKey(outputKey: string): boolean {
  if (outputKey === 'pnl' || outputKey === 'amt') return true
  if (outputKey.startsWith('reg.') && outputKey !== 'reg.n') return true
  if (/^h:.+\.(ret|contribution|pnl)$/.test(outputKey)) return true
  if (/^fc:[^.]+$/.test(outputKey)) return true
  return false
}

function signColor(text: string): string {
  const t = text.trim()
  if (t.startsWith(MINUS) || t.startsWith('-')) return PNL_COLORS.loss
  if (t.startsWith('+')) return PNL_COLORS.gain
  return PNL_COLORS.flat
}

const escapeHtml = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

function preprocess(markdown: string): string {
  return markdown.replace(
    MARKER,
    (_m, key: string, text: string) => `<span data-k="${escapeHtml(key)}">${escapeHtml(text)}</span>`,
  )
}

/** 섹션 제목 → 스펙 블록 스타일 클래스 */
function sectionClass(title: string): string | null {
  if (title.includes('출처')) return 'rp-report-sources'
  if (title.includes('헤지')) return 'rp-report-hedge'
  return null
}

const NUMERIC_CELL = /^[+\-−]?[\d.,]+\s*(%p|%|억 원|개|영업일)?$/

function decorate(root: HTMLElement): void {
  const doc = root.ownerDocument

  // 1) 맨 앞 h1과 바로 뒤 부제 문단은 화면 머리말이 대신 그린다.
  const first = root.firstElementChild
  if (first?.tagName === 'H1') {
    const next = first.nextElementSibling
    if (next?.tagName === 'P') next.remove()
    first.remove()
  }

  // 2) h2 섹션별 클래스
  let current: string | null = null
  for (const el of Array.from(root.children)) {
    if (el.tagName === 'H2') {
      current = sectionClass(el.textContent ?? '')
      continue
    }
    if (current) el.classList.add(current)
  }

  // 3) 수치 마커 → 클릭 가능한 수치
  for (const span of Array.from(root.querySelectorAll<HTMLElement>('span[data-k]'))) {
    const outKey = span.dataset.k ?? ''
    const text = (span.textContent ?? '').split('-').join(MINUS)
    const calcKey = calcKeyFor(outKey)
    const color = isPnlKey(outKey) ? signColor(text) : null
    const el = doc.createElement(calcKey ? 'button' : 'span')
    el.className = calcKey ? 'rp-report-num' : 'rp-report-val'
    if (color) el.classList.add('rp-report-pnl')
    if (calcKey) {
      el.setAttribute('type', 'button')
      el.dataset.calcKey = calcKey
    }
    if (color) el.style.color = color
    el.textContent = text
    span.replaceWith(el)
  }

  // 4) 표: 모든 본문 셀이 수치인 열만 오른쪽 정렬
  for (const table of Array.from(root.querySelectorAll('table'))) {
    const bodyRows = Array.from(table.querySelectorAll('tbody tr'))
    const cols = table.querySelectorAll('thead th').length
    for (let c = 0; c < cols; c++) {
      const cells = bodyRows.map((tr) => tr.children[c]).filter((x): x is Element => !!x)
      const numeric = cells.length > 0 && cells.every((td) => NUMERIC_CELL.test((td.textContent ?? '').trim()))
      if (!numeric) continue
      table.querySelectorAll(`tr > :nth-child(${c + 1})`).forEach((cell) => cell.classList.add('rp-num-col'))
    }
  }

  // 5) 외부 링크는 새 탭으로
  for (const a of Array.from(root.querySelectorAll('a[href]'))) {
    a.setAttribute('target', '_blank')
    a.setAttribute('rel', 'noopener noreferrer')
  }
}

export function renderReport(markdown: string): string {
  const raw = marked.parse(preprocess(markdown), { async: false, gfm: true, breaks: true })
  const clean = DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } })
  const doc = new DOMParser().parseFromString(`<div id="rp-root">${clean}</div>`, 'text/html')
  const root = doc.getElementById('rp-root')
  if (!root) return clean
  decorate(root)
  return root.innerHTML
}

/** 마크다운에 출처 섹션이 이미 있는지 (없으면 화면이 citations로 그린다) */
export function hasSourcesSection(markdown: string): boolean {
  return /^#{1,3}\s.*출처/m.test(markdown)
}
