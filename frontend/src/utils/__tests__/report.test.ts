import { describe, expect, it } from 'vitest'
import { calcKeyFor, hasSourcesSection, isPnlKey, renderReport } from '../report'

const render = (md: string) => {
  const div = document.createElement('div')
  div.innerHTML = renderReport(md)
  return div
}

describe('calcKeyFor', () => {
  it('outputs 키를 S5 entries 키로 바꾼다', () => {
    expect(calcKeyFor('pnl')).toBe('pnl')
    expect(calcKeyFor('range.low')).toBe('range')
    expect(calcKeyFor('reg.median')).toBe('reg')
    expect(calcKeyFor('h:KR_SEMI.contribution')).toBe('h:KR_SEMI')
    expect(calcKeyFor('fc:USDKRW.share')).toBe('fc:USDKRW')
    expect(calcKeyFor('f:DGS10')).toBe('f:DGS10')
  })
  it('계산 근거가 없는 키는 null', () => {
    expect(calcKeyFor('horizon')).toBeNull()
    expect(calcKeyFor('aum')).toBeNull()
    expect(calcKeyFor('rule.fx')).toBeNull()
  })
  it('손익색 대상 판정', () => {
    expect(isPnlKey('pnl')).toBe(true)
    expect(isPnlKey('h:KR_SEMI.ret')).toBe(true)
    expect(isPnlKey('h:KR_SEMI.weight')).toBe(false)
    expect(isPnlKey('range.low')).toBe(false)
    expect(isPnlKey('f:USDKRW')).toBe(false)
    expect(isPnlKey('fc:USDKRW.share')).toBe(false)
  })
})

describe('renderReport', () => {
  it('수치 마커를 클릭 가능한 버튼으로 바꾸고 유니코드 마이너스·손익색을 적용한다', () => {
    const root = render('예상 손익은 <!--k:pnl-->-3.8%<!--/k-->입니다.')
    const btn = root.querySelector<HTMLButtonElement>('button.rp-report-num')
    expect(btn).not.toBeNull()
    expect(btn!.dataset.calcKey).toBe('pnl')
    expect(btn!.textContent).toBe('−3.8%')
    expect(btn!.style.color).toBe('rgb(30, 91, 216)')
  })

  it('계산 근거가 없는 키는 클릭할 수 없는 span으로 둔다', () => {
    const root = render('분석 기간 <!--k:horizon-->20영업일<!--/k-->')
    expect(root.querySelector('button')).toBeNull()
    expect(root.querySelector('span.rp-report-val')?.textContent).toBe('20영업일')
  })

  it('맨 앞 h1과 부제 문단은 제거한다', () => {
    const root = render('# 제목\n\n부제 · 계산 ID `x`\n\n## 1. 요약\n\n본문')
    expect(root.querySelector('h1')).toBeNull()
    expect(root.textContent).not.toContain('부제')
    expect(root.querySelector('h2')?.textContent).toBe('1. 요약')
  })

  it('출처·헤지 섹션에 스타일 클래스를 붙인다', () => {
    const root = render('## 4. 헤지 제안\n\n- **환헤지**\n\n## 5. 데이터 출처\n\n[1] FRED\n[2] ECOS')
    expect(root.querySelector('ul')?.classList.contains('rp-report-hedge')).toBe(true)
    const src = root.querySelector('p.rp-report-sources')
    expect(src).not.toBeNull()
    expect(src!.querySelectorAll('br').length).toBe(1)
  })

  it('수치 열만 오른쪽 정렬 클래스', () => {
    const root = render('| 자산 | 비중 | 근거 |\n| --- | --- | --- |\n| 반도체 | 14.0% | 관세 |')
    const cells = root.querySelectorAll('tbody td')
    expect(cells[0]!.classList.contains('rp-num-col')).toBe(false)
    expect(cells[1]!.classList.contains('rp-num-col')).toBe(true)
    expect(cells[2]!.classList.contains('rp-num-col')).toBe(false)
  })

  it('스크립트·이벤트 핸들러를 제거한다', () => {
    const root = render('안녕 <img src=x onerror="alert(1)"><script>alert(2)</script> [링크](javascript:alert(3))')
    expect(root.querySelector('script')).toBeNull()
    expect(root.querySelector('img')?.getAttribute('onerror')).toBeNull()
    expect(root.querySelector('a')?.getAttribute('href') ?? '').not.toContain('javascript')
  })

  it('출처 섹션 유무', () => {
    expect(hasSourcesSection('## 5. 데이터 출처\n')).toBe(true)
    expect(hasSourcesSection('## 1. 요약\n')).toBe(false)
  })
})
