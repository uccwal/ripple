"""화면 캡처 (Playwright). 사용: python scripts/e2e_shots.py <base_url> <out_dir> [run_id ...]

주요 화면(대시보드·데이터·실행 이력·포트폴리오)과 지정한 실행의 4개 탭, 계산 근거 패널을 1440px 로 캡처하고
브라우저 콘솔 오류·실패한 요청을 JSON 으로 표준 출력에 남긴다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

base = sys.argv[1].rstrip("/")
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
run_ids = sys.argv[3:]
report: dict = {"console": [], "pages": {}}


def shoot(page, path: str, name: str, *, full: bool = True, wait: int = 1500) -> None:
    page.goto(base + path, wait_until="networkidle")
    page.wait_for_timeout(wait)
    page.screenshot(path=str(out / f"{name}.png"), full_page=full)
    report["pages"][name] = {"url": page.url, "title": page.title(), "text_len": len(page.inner_text("body"))}


with sync_playwright() as p:
    import os

    exe = os.environ.get("E2E_CHROMIUM") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: report["console"].append({"type": m.type, "text": m.text}) if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: report["console"].append({"type": "pageerror", "text": str(e)}))
    page.on("requestfailed", lambda r: report["console"].append({"type": "requestfailed", "text": r.url}))

    shoot(page, "/", "01_dashboard")
    shoot(page, "/data", "02_data")
    shoot(page, "/runs", "03_runs")
    shoot(page, "/portfolios", "04_portfolios")
    shoot(page, "/backtest", "05_backtest")
    shoot(page, "/new", "06_new")
    for i, rid in enumerate(run_ids):
        for tab in ("path", "scen", "result", "report"):
            shoot(page, f"/runs/{rid}?tab={tab}", f"1{i}_{tab}_{rid[-4:]}", wait=2500)
    if run_ids:
        shoot(page, f"/api/runs/{run_ids[0]}/report?format=html", f"19_report_html_{run_ids[0][-4:]}", wait=800)
        page.goto(f"{base}/runs/{run_ids[0]}?tab=result", wait_until="networkidle")
        page.wait_for_timeout(1500)
        btn = page.get_by_label("포트폴리오 예상 손익").first
        if btn.count():
            btn.click()
            page.wait_for_timeout(1200)
            page.screenshot(path=str(out / "20_calc_panel.png"), full_page=False)
    browser.close()

print(json.dumps(report, ensure_ascii=False))
