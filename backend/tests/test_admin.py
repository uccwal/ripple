"""관리용 수집 API: 토큰 검증과 백그라운드 시작."""
from fastapi.testclient import TestClient

from app import collect
from app.config import settings
from app.main import app


def test_admin_disabled_without_token_setting(monkeypatch):
    monkeypatch.setattr(settings.__class__, "admin_token", property(lambda self: None), raising=False)
    with TestClient(app) as c:
        assert c.post("/api/admin/collect").status_code == 404


def test_admin_collect_requires_token_and_starts(monkeypatch):
    monkeypatch.setattr(settings.__class__, "admin_token", property(lambda self: "secret"), raising=False)
    calls = []
    monkeypatch.setattr(collect, "start_background", lambda since, only: calls.append((since, only)) or True)
    with TestClient(app) as c:
        assert c.post("/api/admin/collect", headers={"X-Admin-Token": "nope"}).status_code == 403
        r = c.post("/api/admin/collect", json={"only": ["fred"]}, headers={"X-Admin-Token": "secret"})
        assert r.status_code == 202 and r.json()["only"] == ["fred"]
        assert calls == [(None, ["fred"])]
        st = c.get("/api/admin/collect/status", headers={"X-Admin-Token": "secret"}).json()
        assert st["running"] is False


def test_collect_run_skips_without_keys():
    reports = collect.run(only=["fred", "ecos"])
    assert {r["collector"] for r in reports} == {"fred", "ecos", "bok_rate_events", "fed_rate_events", "localize"}
    assert all(r["status"] == "skipped" for r in reports)  # 키 없음 · offline


def test_data_status_public():
    with TestClient(app) as c:
        d = c.get("/api/data/status").json()
        assert d["llm_mode"] == "offline" and d["admin_enabled"] is False
        ids = {x["series_id"] for x in d["series"]}
        assert {"USDKRW", "KOSPI", "DGS10"} <= ids
        k = next(x for x in d["series"] if x["series_id"] == "KOSPI")
        assert k["synthetic"] and k["in_use"] and k["role"] == "factor" and k["count"] > 2000
        assert "KOSPI" in d["synthetic_remaining"]
        assert any(e["is_demo"] for e in d["events"])
        assert {c["name"] for c in d["collectors"]} >= {"fred", "ecos", "krx_prices"}


def test_ensure_columns_adds_missing(tmp_path):
    from sqlalchemy import inspect, text

    from app import db
    eng = db.make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE policy_event (event_id VARCHAR(64) PRIMARY KEY, country VARCHAR(8), type VARCHAR(16), title VARCHAR(300), announced_at DATE)"))
    db.init_db(eng)
    cols = {c["name"] for c in inspect(eng).get_columns("policy_event")}
    assert {"title_orig", "relevance", "summary", "is_demo"} <= cols


def test_localize_offline_noop():
    from app.localize import localize_pending
    assert localize_pending() == {"done": 0, "failed": 0, "skipped": "offline"}


def test_derive_bok_rate_events(session):
    from datetime import date

    from app.derive_events import derive_bok_rate_events
    from app.models.tables import PolicyEvent, Series, SeriesValue
    session.merge(Series(series_id="BOK_BASE_RATE", name="기준금리", source="한국은행 ECOS", unit="%", license="출처 표시"))
    for d, v in [(date(2024, 1, 11), 3.5), (date(2024, 1, 12), 3.5), (date(2024, 10, 11), 3.25), (date(2024, 11, 28), 3.0)]:
        session.merge(SeriesValue(series_id="BOK_BASE_RATE", date=d, value=v))
    session.commit()
    out = derive_bok_rate_events()
    assert out["created"] == 2 and out["total"] == 2
    ev = session.get(PolicyEvent, "bok_rate_20241011")
    assert ev.country == "KR" and ev.type == "rate" and ev.value == -0.25 and "인하" in ev.title and ev.value_text == "−0.25%p"
    assert derive_bok_rate_events()["created"] == 0  # 멱등


def test_factor_series_incomplete_detects_short_or_missing(session):
    from sqlalchemy import delete

    from app.models.tables import SeriesValue

    assert collect.factor_series_incomplete() == []  # 합성 시드는 팩터 9개를 모두 11년치로 채운다
    session.execute(delete(SeriesValue).where(SeriesValue.series_id == "DGS2"))
    session.commit()
    try:
        assert collect.factor_series_incomplete() == ["DGS2"]
        assert collect.data_incomplete() is True
    finally:
        from app import seed

        seed.load_synthetic(session, force=True)
        session.commit()
