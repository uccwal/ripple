"""수집기 테스트 설정.

- 네트워크를 쓰지 않는다 (샌드박스에서 외부 API 가 차단되어 있음). 파서는 고정 응답으로, HTTP 는 httpx.MockTransport 로 검증한다.
- DB 는 인메모리 SQLite. app.db 는 import 시점에 settings.database_url 로 엔진을 만들므로 먼저 환경 변수를 둔다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LLM_MODE"] = "offline"
for k in ("FRED_API_KEY", "ECOS_API_KEY", "DATA_GO_KR_API_KEY"):
    os.environ.pop(k, None)

import pytest  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from app import db  # noqa: E402


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db.init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    s = sessionmaker(bind=engine, expire_on_commit=False, future=True)()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def no_sleep(monkeypatch):
    import collectors.base as b

    monkeypatch.setattr(b.time, "sleep", lambda *_: None)
