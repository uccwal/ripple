"""서버 안에서 수집기를 실행한다 (터미널이 없는 PaaS용).

- `POST /api/admin/collect` (헤더 `X-Admin-Token`) → 백그라운드 스레드에서 collectors.run_all 과 같은 수집을 실행
- `COLLECT_DAILY_HOUR_UTC` 가 설정되면 매일 그 시각(UTC)에 자동 수집 (예: 0 → 09:00 KST)
- 상태·마지막 결과는 `GET /api/admin/collect/status`
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone

from .config import REPO_ROOT, settings
from .db import session_scope
from .util import utcnow

log = logging.getLogger("ripple.collect")

if str(REPO_ROOT) not in sys.path:  # collectors 패키지는 저장소 루트에 있다
    sys.path.insert(0, str(REPO_ROOT))

_lock = threading.Lock()
_state: dict = {"running": False, "started_at": None, "finished_at": None, "reports": [], "error": None,
                "next_scheduled_at": None}


def status() -> dict:
    return dict(_state)


def run(since: date | None = None, only: list[str] | None = None) -> list[dict]:
    """수집기를 순서대로 실행하고 보고서 목록을 돌려준다. 동시 실행은 막는다."""
    if not _lock.acquire(blocking=False):
        raise RuntimeError("이미 수집이 진행 중입니다")
    _state.update(running=True, started_at=utcnow().isoformat(), finished_at=None, reports=[], error=None)
    try:
        from collectors import run_all  # noqa: PLC0415

        reports = []
        for c in run_all.REGISTRY:
            if only and c.name not in only:
                continue
            rep = run_all.run_one(c, session_scope, since.isoformat() if since else None, None, settings)
            log.info(rep.line())
            reports.append({"collector": rep.collector, "status": rep.status, "message": rep.message, "counts": rep.counts})
            _state["reports"] = list(reports)
        return reports
    except Exception as e:  # noqa: BLE001
        _state["error"] = f"{type(e).__name__}: {e}"
        log.exception("수집 실패")
        raise
    finally:
        _state.update(running=False, finished_at=utcnow().isoformat())
        _lock.release()


def start_background(since: date | None = None, only: list[str] | None = None) -> bool:
    if _state["running"]:
        return False
    threading.Thread(target=_safe_run, args=(since, only), daemon=True, name="collect").start()
    return True


def _safe_run(since, only) -> None:
    try:
        run(since, only)
    except Exception:  # noqa: BLE001
        pass  # run() 이 상태에 기록


def _seconds_until(hour_utc: int) -> float:
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def start_scheduler() -> None:
    """COLLECT_DAILY_HOUR_UTC 가 있으면 매일 그 시각에 수집한다."""
    hour = settings.collect_daily_hour_utc
    if hour is None:
        return

    def loop() -> None:
        while True:
            wait = _seconds_until(hour)
            _state["next_scheduled_at"] = (datetime.now(timezone.utc) + timedelta(seconds=wait)).isoformat()
            time.sleep(wait)
            log.info("예약 수집 시작 (%02d:00 UTC)", hour)
            _safe_run(None, None)

    threading.Thread(target=loop, daemon=True, name="collect-scheduler").start()
    log.info("일일 수집 예약: 매일 %02d:00 UTC", hour)
