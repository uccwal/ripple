import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT.parent / 'test_ripple.db'}")
os.environ["LLM_MODE"] = "offline"

import pytest  # noqa: E402

from app import db, seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    """세션 전체에서 한 번: 테이블 생성 + 가상 포트폴리오·이벤트·합성 시계열."""
    path = ROOT.parent / "test_ripple.db"
    for p in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if p.exists():
            p.unlink()
    db.init_db()
    with db.session_scope() as s:
        seed.load_portfolios(s)
        seed.load_events(s)
        seed.load_synthetic(s, force=True)
    yield
    for p in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if p.exists():
            p.unlink()


@pytest.fixture
def session():
    s = db.SessionLocal()
    try:
        yield s
    finally:
        s.close()
