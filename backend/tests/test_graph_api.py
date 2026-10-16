"""그래프 실행(offline) + API 통합 테스트."""
import re

import pytest
from fastapi.testclient import TestClient

from app import graph, runner
from app.main import app
from app.models.tables import Run


def _wait(client: TestClient, run_id: str) -> dict:
    # 실행은 백그라운드 스레드. SSE 스트림이 run_finished로 끝날 때까지 읽는다.
    with client.stream("GET", f"/api/runs/{run_id}/stream") as r:
        events = []
        for line in r.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
            if events and events[-1] == "run_finished" and line == "":
                break
    assert "run_finished" in events
    return client.get(f"/api/runs/{run_id}").json()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_meta_and_lists(client):
    m = client.get("/api/meta").json()
    assert m["service"] == "RIPPLE" and m["llm_mode"] == "offline" and m["synthetic_data"] is True
    evs = client.get("/api/events?country=US&type=tariff").json()
    assert all(e["country"] == "US" and e["type"] == "tariff" for e in evs) and evs
    pfs = client.get("/api/portfolios").json()
    assert {p["portfolio_id"] for p in pfs} == {"pf_a", "pf_b"}
    pf = client.get("/api/portfolios/pf_a").json()
    assert sum(h["weight"] for h in pf["holdings"]) == pytest.approx(100)


def test_event_run_end_to_end(client):
    rid = client.post("/api/runs", json={"entry": "event", "event_id": "ev_demo_us_semis_tariff", "portfolio_id": "pf_a"}).json()["run_id"]
    d = _wait(client, rid)
    assert d["status"] in ("done", "partial")
    assert [s["status"] for s in d["steps"]] == ["done"] * 7
    assert d["event"]["type"] == "tariff"
    assert 1 <= len(d["impact_paths"]) <= 3 and all(len(p["steps"]) <= 4 for p in d["impact_paths"])
    assert d["graph"]["nodes"] and d["graph"]["edges"]
    assert d["scenario"]["shocks"] and d["result"]["portfolio_pnl"] < 0
    assert d["validation"]["passed"]
    # 보고서: 숫자는 모두 마커 안에 있어야 한다 (R4)
    md = d["report"]["markdown"]
    assert "<!--k:pnl-->" in md and "{{" not in md
    assert d["report"]["citations"]
    # 계산 근거 패널
    cl = client.get(f"/api/runs/{rid}/calc-log").json()
    assert cl["calc_id"] == d["result"]["calc_log_id"]
    for key in ("pnl", "amt", "range", "reg", "fc:USDKRW") + tuple(f"h:{a['asset_id']}" for a in d["result"]["by_asset"]):
        assert key in cl["entries"], key
    e = cl["entries"]["pnl"]
    assert e["value_text"].startswith("−") and e["rows"] and e["columns"]
    # 보고서 다운로드
    r = client.get(f"/api/runs/{rid}/report")
    assert r.status_code == 200 and "<!--k:" not in r.text and "attachment" in r.headers["content-disposition"]
    h = client.get(f"/api/runs/{rid}/report?format=html")
    assert h.status_code == 200 and 'class="num loss"' in h.text
    # 이벤트 목록에 최근 분석이 붙는다
    ev = next(e for e in client.get("/api/events").json() if e["event_id"] == "ev_demo_us_semis_tariff")
    assert ev["last_run"]["run_id"] == rid
    # 실행 이력
    assert any(x["run_id"] == rid and x["validation_status"] in ("pass", "warn") for x in client.get("/api/runs").json())


def test_scenario_run_and_recalc(client):
    rid = client.post("/api/runs", json={"entry": "scenario", "scenario_text": "유가 30% 급등 + 원화 20% 약세", "portfolio_id": "pf_a"}).json()["run_id"]
    d = _wait(client, rid)
    assert d["status"] == "done"
    assert [s["status"] for s in d["steps"][:2]] == ["skip", "skip"]
    shocks = {s["variable"]: s["change"] for s in d["scenario"]["shocks"]}
    assert shocks == {"USDKRW": 20.0, "WTI": 30.0}
    assert any(s["over_hist"] for s in d["scenario"]["shocks"])  # 원화 20%는 과거 최대 초과 (합성 데이터 기준)
    assert d["graph"] is None and d["impact_paths"] == []
    # 충격값 수정 → 새 run, Regime Finder부터
    rid2 = client.patch(f"/api/runs/{rid}/scenario", json={"shocks": [{"variable": "USDKRW", "change": 2.0}]}).json()["run_id"]
    d2 = _wait(client, rid2)
    assert d2["parent_run_id"] == rid and d2["status"] == "done"
    assert {s["variable"]: s["change"] for s in d2["scenario"]["shocks"]} == {"USDKRW": 2.0, "WTI": 30.0}
    assert d2["steps"][2]["note"].startswith("이전 실행 결과 재사용")
    assert d2["result"]["portfolio_pnl"] != d["result"]["portfolio_pnl"]


def test_as_of_point_in_time(client):
    rid = client.post("/api/runs", json={"entry": "event", "event_id": "ev_hist_2019_jp_export", "portfolio_id": "pf_a", "as_of": "2019-07-01"}).json()["run_id"]
    d = _wait(client, rid)
    assert d["status"] in ("done", "partial") and d["as_of"] == "2019-07-01"
    assert all(r["end"] <= "2019-07-01" for r in d["regimes"])


def test_validation_errors(client):
    assert client.post("/api/runs", json={"entry": "event", "portfolio_id": "pf_a"}).status_code == 422
    assert client.post("/api/runs", json={"entry": "scenario", "scenario_text": " ", "portfolio_id": "pf_a"}).status_code == 422
    assert client.post("/api/runs", json={"entry": "event", "event_id": "nope", "portfolio_id": "pf_a"}).status_code == 404
    assert client.get("/api/runs/nope").status_code == 404
    rid = client.post("/api/runs", json={"entry": "scenario", "scenario_text": "날씨가 좋다", "portfolio_id": "pf_a"}).json()["run_id"]
    d = _wait(client, rid)
    assert d["status"] == "failed" and "변수" in d["error"]
    assert d["steps"][2]["status"] == "failed"


def test_event_run_has_actual_and_cross_portfolio(client):
    """과거 이벤트 분석에는 사후 검증과 포트폴리오 비교가 붙고, 보고서에 그 섹션이 들어간다."""
    rid = client.post("/api/runs", json={"entry": "event", "event_id": "ev_hist_2022_us_chip_export", "portfolio_id": "pf_a"}).json()["run_id"]
    d = _wait(client, rid)
    assert d["status"] in ("done", "partial") and d["auto"] is False
    act = d["result"]["actual"]
    assert act and act["complete"] and act["direction_hit"] in (True, False)
    assert [x["portfolio_id"] for x in d["result"]["cross_portfolio"]] == ["pf_a", "pf_b"]
    md = d["report"]["markdown"]
    assert "사후 검증" in md and "다른 모델 포트폴리오" in md
    bt = client.get("/api/backtest").json()
    assert bt["n_cases"] >= 1 and bt["cases"][0]["run_id"] == rid
    ev = next(e for e in client.get("/api/events?country=US").json() if e["event_id"] == "ev_hist_2022_us_chip_export")
    assert ev["last_run"]["run_id"] == rid and ev["last_run"]["actual_pnl"] is not None
    m = client.get("/api/meta").json()
    assert m["radar"]["backtest"]["n_cases"] >= 1 and "quality_issues" in m["radar"]


def test_auto_analyze_picks_recent_high_events(client):
    from datetime import date

    from app import auto_analyze, db
    from app.models.tables import PolicyEvent, Run

    with db.session_scope() as s:
        s.merge(PolicyEvent(event_id="ev_auto_test", country="KR", type="tariff", title="자동 분석 테스트 관세 10%", summary="t",
                            targets=["steel"], value=10.0, value_text="관세율 10%", announced_at=date.today(), source="test",
                            source_url="", license="", raw_text="철강 관세 10% 부과", is_demo=False, relevance="high"))
    res = auto_analyze.auto_analyze(max_runs=1, days=7)
    assert res["started"] == 1 and res["done"] == 1
    with db.session_scope() as s:
        run = s.scalars(__import__("sqlalchemy").select(Run).where(Run.event_id == "ev_auto_test")).one()
        assert run.state.get("auto") is True and run.status in ("done", "partial")
        assert run.state["result"]["actual"] is None  # 오늘 발표 → 아직 실제 데이터 없음
    # 이미 분석된 이벤트는 다시 고르지 않는다
    assert auto_analyze.auto_analyze(max_runs=5, days=7)["started"] == 0
    assert client.get("/api/admin/analyze/run?token=x").status_code in (403, 404)
