"""보고서 인쇄용 HTML (브라우저 인쇄 → PDF). 디자인 토큰(navy #16264A, 손익색)을 따른다."""
from __future__ import annotations

import html
import re

import markdown as md_lib


def render_html(md: str, state: dict, portfolio) -> str:
    # 수치 마커 → 손익색 span
    def rep(m: re.Match) -> str:
        key, val = m.group(1), m.group(2)
        cls = "num"
        if val.startswith("−"):
            cls += " loss"
        elif val.startswith("+"):
            cls += " gain"
        return f'<span class="{cls}" data-key="{html.escape(key)}">{html.escape(val)}</span>'

    body_md = re.sub(r"<!--k:([^>]*)-->(.*?)<!--/k-->", rep, md, flags=re.S)
    body = md_lib.markdown(body_md, extensions=["tables"])
    v = state.get("validation") or {}
    badge = {"pass": ("✓ 검증 통과", "#E5F4EC", "#1B7F4B"), "warn": ("⚠ 경고 포함", "#FFF4D1", "#8A5E00"),
             "fail": ("! 검증 실패", "#FDECEA", "#B42318")}.get(v.get("status"), ("—", "#EEF1F7", "#16264A"))
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>RIPPLE 보고서 · {html.escape(state.get('title') or '')}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
 @page {{ size: A4; margin: 18mm 16mm; }}
 body {{ font-family: "Pretendard Variable", Pretendard, -apple-system, sans-serif; font-size: 13px; line-height: 1.75; color: #141A24; max-width: 820px; margin: 0 auto; padding: 40px 56px 48px; word-break: keep-all; background: #fff; }}
 .kicker {{ font-size: 12px; font-weight: 700; letter-spacing: .12em; color: #16264A; }}
 h1 {{ font-size: 22px; font-weight: 700; margin: 4px 0 6px; }}
 .meta {{ font-size: 12px; color: #7A8394; padding-bottom: 12px; border-bottom: 2px solid #16264A; margin-bottom: 20px; display: flex; gap: 12px; align-items: center; }}
 .badge {{ display: inline-block; height: 22px; line-height: 22px; padding: 0 8px; border-radius: 4px; font-size: 12px; font-weight: 600; background: {badge[1]}; color: {badge[2]}; }}
 h2 {{ font-size: 15px; font-weight: 700; margin: 24px 0 8px; color: #16264A; }}
 h3 {{ font-size: 13px; font-weight: 700; margin: 16px 0 6px; color: #4A5363; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 12.5px; margin: 8px 0 12px; }}
 th {{ text-align: left; font-weight: 600; color: #7A8394; background: #F8F9FA; padding: 6px 10px; border-top: 1px solid #141A24; border-bottom: 1px solid #E3E6EB; }}
 td {{ padding: 6px 10px; border-bottom: 1px solid #EEF0F3; }}
 td:nth-child(n+2), th:nth-child(n+2) {{ text-align: right; }}
 .num {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
 .gain {{ color: #D23F31; }} .loss {{ color: #1E5BD8; }}
 code {{ font-family: ui-monospace, Menlo, monospace; font-size: 11px; background: #F5F6F8; padding: 1px 4px; border-radius: 3px; }}
 li {{ margin: 2px 0; }}
 .foot {{ margin-top: 28px; font-size: 11px; color: #A3AAB6; }}
 .print {{ position: fixed; top: 12px; right: 12px; height: 32px; padding: 0 14px; border: 1px solid #CDD2DA; border-radius: 6px; background: #fff; font: 600 13px/32px inherit; cursor: pointer; }}
 @media print {{ .print {{ display: none; }} body {{ padding: 0; }} }}
</style></head><body>
<button class="print" onclick="window.print()">PDF로 저장 (인쇄)</button>
<div class="kicker">RIPPLE 정책 파급 분석 보고서</div>
<div class="meta"><span>{html.escape(portfolio.name if portfolio else '')}</span><span>·</span><span>분석 기간 {run.horizon_days}영업일</span><span class="badge">{badge[0]}</span></div>
{body}
<div class="foot">이 보고서의 모든 수치는 Risk Engine 계산 로그(calc_log)에서 인용했습니다. LLM은 문장만 작성했습니다. · RIPPLE</div>
</body></html>"""
