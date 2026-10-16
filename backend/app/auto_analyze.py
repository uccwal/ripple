"""수집 직후 자동 사전분석.

관련성 high · 최근 N일 · 아직 분석 실행이 없는 정책 이벤트를 기본 포트폴리오로 분석해 둔다.
대시보드를 열면 이벤트 카드에 예상 손익이 이미 붙어 있고, 심사·시연 때 빈 화면이 아니다.
수집 스레드 안에서 순차 실행한다 (실행 1건 ≈ 40~60초, 상한 AUTO_ANALYZE_MAX).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select

from . import graph
from .config import settings
from .db import session_scope
from .models.tables import PolicyEvent, Portfolio, Run

log = logging.getLogger("ripple.auto")
ACTIVE = ("queued", "running", "done", "partial")


def pending_events(session, days: int, limit: int) -> list[PolicyEvent]:
    """자동 분석 대상: 관련성 high, 예시 아님, 최근 days 일, 분석 실행이 없는 이벤트 (최신순)."""
    analyzed = set(session.scalars(select(Run.event_id).where(Run.event_id.is_not(None), Run.status.in_(ACTIVE))))
    since = date.today() - timedelta(days=days)
    q = (select(PolicyEvent).where(PolicyEvent.relevance == "high", PolicyEvent.is_demo.is_(False),
                                   PolicyEvent.announced_at >= since).order_by(PolicyEvent.announced_at.desc()))
    return [e for e in session.scalars(q) if e.event_id not in analyzed][:limit]


def auto_analyze(max_runs: int | None = None, days: int | None = None, portfolio_id: str | None = None) -> dict:
    limit = settings.auto_analyze_max if max_runs is None else max_runs
    days = settings.auto_analyze_days if days is None else days
    if limit <= 0:
        return {"started": 0, "done": 0, "failed": 0, "skipped": "disabled"}
    run_ids: list[str] = []
    with session_scope() as s:
        pf_id = portfolio_id or settings.auto_analyze_portfolio
        if s.get(Portfolio, pf_id) is None:
            first = s.scalars(select(Portfolio).order_by(Portfolio.portfolio_id)).first()
            if first is None:
                return {"started": 0, "done": 0, "failed": 0, "skipped": "포트폴리오 없음"}
            pf_id = first.portfolio_id
        targets = pending_events(s, days, limit)
        for ev in targets:
            run = graph.create_run(s, "event", pf_id, ev.event_id, None, 20)
            run.state = {**run.state, "auto": True}
            s.commit()
            run_ids.append(run.run_id)
            log.info("자동 분석 예약: %s ← %s", run.run_id, ev.title[:40])
    done = failed = 0
    for rid in run_ids:
        graph.execute(rid)  # 동기 실행 (수집 스레드)
        with session_scope() as s:
            status = s.get(Run, rid).status
        if status in ("done", "partial"):
            done += 1
        else:
            failed += 1
    log.info("자동 분석: 시작 %d · 완료 %d · 실패 %d", len(run_ids), done, failed)
    return {"started": len(run_ids), "done": done, "failed": failed}
