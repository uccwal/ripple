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
        # 시계열에서 파생하는 이벤트 (한국은행 금통위·미국 FOMC 기준금리 결정)
        from .derive_events import derive_bok_rate_events, derive_fed_rate_events  # noqa: PLC0415

        for name, fn, msg in (("bok_rate_events", derive_bok_rate_events, "한국은행 기준금리 결정 이벤트 (ECOS 시계열 파생)"),
                              ("fed_rate_events", derive_fed_rate_events, "미국 연준(FOMC) 기준금리 결정 이벤트 (FRED 시계열 파생)")):
            try:
                d = fn()
                reports.append({"collector": name, "status": "skipped" if d.get("skipped") else "ok",
                                "message": msg + (f" — {d['skipped']}" if d.get("skipped") else ""),
                                "counts": {k: v for k, v in d.items() if k != "skipped"}})
            except Exception as e:  # noqa: BLE001
                log.exception("기준금리 이벤트 파생 실패 (%s)", name)
                reports.append({"collector": name, "status": "error", "message": f"{type(e).__name__}: {e}", "counts": {}})
            _state["reports"] = list(reports)
        # 수집된 외국어 이벤트를 한국어로 구조화 (LLM 모드일 때만)
        from .localize import localize_pending  # noqa: PLC0415

        try:
            loc = localize_pending()
            reports.append({"collector": "localize", "status": "skipped" if loc.get("skipped") else "ok",
                            "message": "이벤트 한국어 구조화" + (f" ({loc['skipped']})" if loc.get("skipped") else ""),
                            "counts": {k: v for k, v in loc.items() if k != "skipped"}})
        except Exception as e:  # noqa: BLE001
            log.exception("한국어 구조화 실패")
            reports.append({"collector": "localize", "status": "error", "message": f"{type(e).__name__}: {e}", "counts": {}})
        _state["reports"] = list(reports)
        # 관련성 high 신규 이벤트 자동 사전분석 (대시보드에 예상 손익이 미리 붙도록)
        from .auto_analyze import auto_analyze  # noqa: PLC0415

        try:
            a = auto_analyze()
            reason = a.get("skipped") or ("대상 없음" if not a.get("started") else None)
            reports.append({"collector": "auto_analyze", "status": "skipped" if reason else "ok",
                            "message": "신규 이벤트 자동 사전분석" + (f" ({reason})" if reason else ""),
                            "counts": {k: v for k, v in a.items() if k != "skipped"}})
        except Exception as e:  # noqa: BLE001
            log.exception("자동 사전분석 실패")
            reports.append({"collector": "auto_analyze", "status": "error", "message": f"{type(e).__name__}: {e}", "counts": {}})
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


RETRY_HOURS = 2  # 합성 시계열이 남아 있거나 수집기가 실패하면 이 간격으로 다시 시도


def synthetic_remaining() -> bool:
    from sqlalchemy import func, select  # noqa: PLC0415

    from .models.tables import Series  # noqa: PLC0415

    with session_scope() as s:
        return bool(s.scalar(select(func.count()).select_from(Series).where(Series.source.like("SYNTHETIC%"))))


def factor_series_incomplete() -> list[str]:
    """팩터 카탈로그의 시리즈 중 없거나 회귀 최소 관측치(beta_min_obs)보다 짧은 것. 새 팩터를 추가하면 전체 기간 수집이 필요하다."""
    from sqlalchemy import func, select  # noqa: PLC0415

    from .engine.catalog import FACTORS  # noqa: PLC0415
    from .models.tables import SeriesValue  # noqa: PLC0415

    with session_scope() as s:
        counts = dict(s.execute(select(SeriesValue.series_id, func.count()).group_by(SeriesValue.series_id)).all())
    return [f.series_id for f in FACTORS if counts.get(f.series_id, 0) < settings.beta_min_obs]


def data_incomplete() -> bool:
    """합성 시계열이 남았거나 팩터 시리즈가 비어 있으면 True (전체 기간 수집 대상)."""
    return synthetic_remaining() or bool(factor_series_incomplete())


def _needs_retry() -> bool:
    if _state.get("error"):
        return True
    if any(r["status"] == "error" for r in _state.get("reports", [])):
        return True
    try:
        return data_incomplete()
    except Exception:  # noqa: BLE001
        return False


def start_scheduler() -> None:
    """COLLECT_DAILY_HOUR_UTC 가 있으면: 기동 직후 한 번, 그 뒤 매일 그 시각에 수집한다.
    합성 시계열이 남아 있거나(= API 키·활용신청 미완료), 팩터 시리즈가 비어 있거나(새 팩터 추가 직후), 실패한 수집기가 있으면
    2시간마다 다시 시도해, 키가 활성화되는 즉시 사람 손 없이 실데이터로 바뀐다."""
    hour = settings.collect_daily_hour_utc
    if hour is None:
        return

    def loop() -> None:
        time.sleep(20)  # 서버가 뜬 뒤
        first = True
        while True:
            if first:
                # 합성 시계열이 남아 있거나 새로 추가된 팩터 시리즈가 비어 있으면 전체 기간(11년)을 받아야 회귀(최소 250일)가 가능하다.
                # 전부 채워져 있으면 최근 N일만 갱신한다.
                full = _needs_retry()
                since = date.today() - timedelta(days=365 * 11 if full else settings.collect_startup_days)
                log.info("기동 수집 시작 (%s)", "전체 기간" if full else f"최근 {settings.collect_startup_days}일")
                _safe_run(since, None)
                first = False
            wait = _seconds_until(hour)
            if _needs_retry():
                wait = min(wait, RETRY_HOURS * 3600)
            _state["next_scheduled_at"] = (datetime.now(timezone.utc) + timedelta(seconds=wait)).isoformat()
            time.sleep(wait)
            log.info("예약 수집 시작")
            # 아직 합성 데이터가 남은 시리즈는 전체 기간을 채워야 하므로 5년치부터
            since = date.today() - timedelta(days=365 * 11) if _needs_retry() else None
            _safe_run(since, None)

    threading.Thread(target=loop, daemon=True, name="collect-scheduler").start()
    log.info("수집 예약: 매일 %02d:00 UTC · 미완료 시 %d시간마다 재시도", hour, RETRY_HOURS)
