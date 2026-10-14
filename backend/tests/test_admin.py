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
    assert {r["collector"] for r in reports} == {"fred", "ecos"}
    assert all(r["status"] == "skipped" for r in reports)
