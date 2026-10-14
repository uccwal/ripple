"""REST + SSE 라우터 (docs/API_CONTRACT.md)."""
from __future__ import annotations

import asyncio
import json
import threading
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import collect, graph, runner
from ..config import settings
from ..db import get_session
from ..engine.catalog import FACTOR_BY_ID
from ..engine.risk import ENGINE_VERSION
from ..models.tables import CalcLog, Holding, PolicyEvent, Portfolio, Run, Series, SeriesValue
from .report_html import render_html

router = APIRouter(prefix="/api")
TYPE_NAME = {"tariff": "관세", "rate": "금리", "regulation": "규제"}
COUNTRY_NAME = {"US": "미국", "KR": "한국", "EU": "EU", "CN": "중국", "JP": "일본"}


# ------------------------------------------------------------------ meta

@router.get("/meta")
def meta(s: Session = Depends(get_session)):
    today = date.today()
    last = s.scalar(select(func.max(SeriesValue.collected_at)))
    sources = s.execute(select(PolicyEvent.source, func.count()).where(PolicyEvent.announced_at == today).group_by(PolicyEvent.source)).all()
    today_cnt = sum(c for _, c in sources)
    yday_cnt = s.scalar(select(func.count()).select_from(PolicyEvent).where(PolicyEvent.announced_at == today - timedelta(days=1))) or 0
    synthetic = bool(s.scalar(select(func.count()).select_from(Series).where(Series.source.like("SYNTHETIC%"))))
    return {
        "service": "RIPPLE", "engine_version": ENGINE_VERSION, "llm_mode": settings.llm_mode,
        "model_default": settings.model_default, "model_impact_mapper": settings.model_impact_mapper,
        "last_collected_at": last.isoformat() if last else None,
        "today_event_count": today_cnt, "today_event_delta": today_cnt - yday_cnt,
        "events_by_source": [{"source": src, "count": c} for src, c in sources],
        "synthetic_data": synthetic,
    }


# ------------------------------------------------------------------ events

def _event_view(e: PolicyEvent, last_run: Run | None) -> dict:
    return {
        "event_id": e.event_id, "country": e.country, "country_name": COUNTRY_NAME.get(e.country, e.country),
        "type": e.type, "type_name": TYPE_NAME.get(e.type, e.type), "title": e.title, "summary": e.summary,
        "targets": e.targets, "value": e.value, "value_text": e.value_text, "announced_at": e.announced_at.isoformat(),
        "source": e.source, "source_url": e.source_url, "is_demo": e.is_demo,
        "title_orig": e.title_orig, "relevance": e.relevance,
        "last_run": ({"run_id": last_run.run_id, "portfolio_pnl": (last_run.state.get("result") or {}).get("portfolio_pnl")}
                     if last_run else None),
    }


def _last_runs_by_event(s: Session) -> dict[str, Run]:
    out: dict[str, Run] = {}
    for r in s.scalars(select(Run).where(Run.event_id.is_not(None), Run.status.in_(["done", "partial"])).order_by(Run.created_at.desc())):
        out.setdefault(r.event_id, r)
    return out


@router.get("/events")
def list_events(country: str | None = None, type: str | None = None, days: int | None = None,
                relevance: str | None = Query(None, description="high | mid | low — 이 등급 이상만"),
                limit: int = Query(200, le=1000), s: Session = Depends(get_session)):
    q = select(PolicyEvent)
    if country:
        q = q.where(PolicyEvent.country == country)
    if relevance in ("high", "mid"):
        allowed = ["high"] if relevance == "high" else ["high", "mid"]
        # 관련성 미평가(None)·예시 이벤트는 항상 포함
        q = q.where((PolicyEvent.relevance.in_(allowed)) | (PolicyEvent.relevance.is_(None)) | (PolicyEvent.is_demo.is_(True)))
    if type:
        q = q.where(PolicyEvent.type == type)
    if days:
        q = q.where(PolicyEvent.announced_at >= date.today() - timedelta(days=days))
    last = _last_runs_by_event(s)
    return [_event_view(e, last.get(e.event_id)) for e in s.scalars(q.order_by(PolicyEvent.announced_at.desc()).limit(limit))]


@router.get("/events/{event_id}")
def get_event(event_id: str, s: Session = Depends(get_session)):
    e = s.get(PolicyEvent, event_id)
    if not e:
        raise HTTPException(404, "이벤트 없음")
    v = _event_view(e, _last_runs_by_event(s).get(event_id))
    v.update({"raw_text": e.raw_text, "collected_at": e.collected_at.isoformat() if e.collected_at else None, "license": e.license})
    return v


# ------------------------------------------------------------------ portfolios

@router.get("/portfolios")
def list_portfolios(s: Session = Depends(get_session)):
    out = []
    for p in s.scalars(select(Portfolio).order_by(Portfolio.portfolio_id)):
        n = s.scalar(select(func.count()).select_from(Holding).where(Holding.portfolio_id == p.portfolio_id))
        out.append({"portfolio_id": p.portfolio_id, "name": p.name, "base_currency": p.base_currency,
                    "description": p.description, "aum": p.aum, "holdings_count": n})
    return out


@router.get("/portfolios/{portfolio_id}")
def get_portfolio(portfolio_id: str, s: Session = Depends(get_session)):
    p = s.get(Portfolio, portfolio_id)
    if not p:
        raise HTTPException(404, "포트폴리오 없음")
    hs = s.scalars(select(Holding).where(Holding.portfolio_id == portfolio_id).order_by(Holding.weight.desc()))
    return {"portfolio_id": p.portfolio_id, "name": p.name, "base_currency": p.base_currency, "description": p.description,
            "aum": p.aum, "holdings": [{"asset_id": h.asset_id, "name": h.name, "asset_class": h.asset_class,
                                        "currency": h.currency, "sector": h.sector, "weight": h.weight} for h in hs]}


# ------------------------------------------------------------------ runs

class RunCreate(BaseModel):
    entry: Literal["event", "scenario"]
    event_id: str | None = None
    scenario_text: str | None = None
    portfolio_id: str
    horizon_days: int = Field(20, ge=5, le=120)
    as_of: date | None = None


class ScenarioPatch(BaseModel):
    shocks: list[dict]


def _start(run_id: str) -> None:
    threading.Thread(target=graph.execute, args=(run_id,), daemon=True, name=f"run-{run_id}").start()


@router.post("/runs", status_code=201)
def create_run(body: RunCreate, s: Session = Depends(get_session)):
    if body.entry == "event" and not body.event_id:
        raise HTTPException(422, "event_id가 필요합니다")
    if body.entry == "scenario" and not (body.scenario_text or "").strip():
        raise HTTPException(422, "scenario_text가 필요합니다")
    try:
        run = graph.create_run(s, body.entry, body.portfolio_id, body.event_id, body.scenario_text, body.horizon_days, body.as_of)
    except ValueError as e:
        raise HTTPException(404, str(e))
    _start(run.run_id)
    return {"run_id": run.run_id}


@router.patch("/runs/{run_id}/scenario")
def patch_scenario(run_id: str, body: ScenarioPatch, s: Session = Depends(get_session)):
    parent = s.get(Run, run_id)
    if not parent or not parent.state.get("scenario"):
        raise HTTPException(404, "수정할 시나리오가 있는 실행이 아닙니다")
    overrides: dict[str, float] = {}
    for item in body.shocks:
        v = item.get("variable")
        if v not in FACTOR_BY_ID:
            raise HTTPException(422, f"알 수 없는 변수: {v}")
        try:
            overrides[v] = float(item["change"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(422, f"충격값 형식 오류: {v}")
    run = graph.create_run(s, parent.entry, parent.portfolio_id, parent.event_id, parent.input_text, parent.horizon_days,
                           parent.as_of, parent=parent, shock_overrides=overrides)
    _start(run.run_id)
    return {"run_id": run.run_id}


def _run_view(s: Session, r: Run) -> dict:
    st = r.state or {}
    pf = s.get(Portfolio, r.portfolio_id)
    out = {
        "run_id": r.run_id, "parent_run_id": r.parent_run_id, "entry": r.entry, "status": r.status, "error": r.error,
        "title": r.title or st.get("title") or r.input_text, "input_text": r.input_text,
        "portfolio": {"portfolio_id": pf.portfolio_id, "name": pf.name, "aum": pf.aum} if pf else None,
        "horizon_days": r.horizon_days, "as_of": (st.get("calc_log") or {}).get("inputs", {}).get("as_of") or (r.as_of.isoformat() if r.as_of else None),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "elapsed_ms": runner.elapsed_ms(r), "llm_mode": r.llm_mode,
        "synthetic_data": any(src.get("synthetic") for src in (st.get("calc_log") or {}).get("inputs", {}).get("sources", [])),
        "event": st.get("event"), "impact_paths": st.get("impact_paths") or [], "graph": st.get("graph"),
        "scenario": st.get("scenario"), "regimes": st.get("regimes") or [], "result": st.get("result"),
        "validation": st.get("validation"), "report": st.get("report"),
        "steps": runner.build_timeline(s, r), "retry_loops": runner.retry_loops(s, r),
    }
    return out


@router.get("/runs")
def list_runs(limit: int = Query(50, le=200), s: Session = Depends(get_session)):
    out = []
    for r in s.scalars(select(Run).order_by(Run.created_at.desc()).limit(limit)):
        pf = s.get(Portfolio, r.portfolio_id)
        st = r.state or {}
        out.append({"run_id": r.run_id, "created_at": r.created_at.isoformat() if r.created_at else None, "entry": r.entry,
                    "title": r.title or st.get("title") or r.input_text, "portfolio_name": pf.name if pf else r.portfolio_id,
                    "portfolio_pnl": (st.get("result") or {}).get("portfolio_pnl"),
                    "validation_status": (st.get("validation") or {}).get("status") or ("fail" if r.status == "failed" else None),
                    "status": r.status})
    return out


@router.get("/runs/{run_id}")
def get_run(run_id: str, s: Session = Depends(get_session)):
    r = s.get(Run, run_id)
    if not r:
        raise HTTPException(404, "실행 없음")
    return _run_view(s, r)


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str):
    q = runner.subscribe(run_id)  # 먼저 구독해야 상태 확인과 run_finished 사이의 틈을 놓치지 않는다
    with next(get_session()) as s:  # type: ignore[attr-defined]
        r = s.get(Run, run_id)
        if not r:
            runner.unsubscribe(run_id, q)
            raise HTTPException(404, "실행 없음")
        if r.status in ("done", "partial", "failed"):
            runner.unsubscribe(run_id, q)
            snapshot = {"run_id": run_id, "status": r.status, "error": r.error, "elapsed_ms": runner.elapsed_ms(r),
                        "current": None, "step": None, "steps": runner.build_timeline(s, r), "retry_loops": runner.retry_loops(s, r)}

            async def done_gen():
                yield _sse("run_finished", snapshot)
            return StreamingResponse(done_gen(), media_type="text/event-stream", headers=_sse_headers())
        snapshot = {"run_id": run_id, "status": r.status, "elapsed_ms": runner.elapsed_ms(r), "current": None, "step": None,
                    "steps": runner.build_timeline(s, r), "retry_loops": runner.retry_loops(s, r)}

    async def gen():
        try:
            yield _sse("snapshot", snapshot)
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {msg['event']}\ndata: {msg['data']}\n\n"
                if msg["event"] == "run_finished":
                    break
        finally:
            runner.unsubscribe(run_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_sse_headers())


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _sse_headers() -> dict:
    return {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


@router.get("/runs/{run_id}/calc-log")
def calc_log(run_id: str, s: Session = Depends(get_session)):
    r = s.get(Run, run_id)
    if not r:
        raise HTTPException(404, "실행 없음")
    c = s.scalar(select(CalcLog).where(CalcLog.run_id == run_id).order_by(CalcLog.created_at.desc()))
    if not c:
        raise HTTPException(404, "계산 로그 없음 (아직 계산 전이거나 실패한 실행)")
    return {"calc_id": c.calc_id, "run_id": run_id, "code_hash": c.code_hash, "engine_version": c.engine_version,
            "created_at": c.created_at.isoformat(), "sources": c.inputs.get("sources", []),
            "entries": c.outputs.get("entries", {}), "inputs": {k: v for k, v in c.inputs.items() if k != "sources"},
            "outputs": c.outputs.get("outputs", {})}


@router.get("/runs/{run_id}/report")
def report(run_id: str, format: Literal["md", "html"] = "md", s: Session = Depends(get_session)):
    r = s.get(Run, run_id)
    if not r or not (r.state or {}).get("report"):
        raise HTTPException(404, "보고서 없음")
    md: str = r.state["report"]["markdown"]
    if format == "html":
        return HTMLResponse(render_html(md, r.state, s.get(Portfolio, r.portfolio_id)))
    clean = _strip_markers(md)
    return Response(clean, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="ripple_{run_id}.md"'})


def _strip_markers(md: str) -> str:
    import re
    return re.sub(r"<!--k:[^>]*-->|<!--/k-->", "", md)


# ------------------------------------------------------------------ series

@router.get("/series/{series_id}")
def series(series_id: str, start: date | None = None, end: date | None = None, s: Session = Depends(get_session)):
    meta = s.get(Series, series_id)
    if not meta:
        raise HTTPException(404, "시계열 없음")
    q = select(SeriesValue.date, SeriesValue.value).where(SeriesValue.series_id == series_id)
    if start:
        q = q.where(SeriesValue.date >= start)
    if end:
        q = q.where(SeriesValue.date <= end)
    pts = s.execute(q.order_by(SeriesValue.date)).all()
    return {"series_id": series_id, "name": meta.name, "unit": meta.unit, "source": meta.source, "license": meta.license,
            "source_url": meta.source_url, "points": [{"date": d.isoformat(), "value": v} for d, v in pts]}


# ------------------------------------------------------------------ admin: 서버 안에서 수집기 실행

def _check_admin(token: str | None) -> None:
    if not settings.admin_token:
        raise HTTPException(404, "관리용 API가 비활성 상태입니다 (ADMIN_TOKEN 미설정)")
    if token != settings.admin_token:
        raise HTTPException(403, "토큰이 올바르지 않습니다")


class CollectRequest(BaseModel):
    since: date | None = None
    only: list[str] | None = None


@router.post("/admin/collect", status_code=202)
def admin_collect(body: CollectRequest | None = None, x_admin_token: str | None = Header(default=None),
                  token: str | None = Query(default=None)):
    """수집기를 백그라운드로 실행한다. 진행 상황은 GET /api/admin/collect/status."""
    _check_admin(x_admin_token or token)
    body = body or CollectRequest()
    if not collect.start_background(body.since, body.only):
        raise HTTPException(409, "이미 수집이 진행 중입니다")
    return {"started": True, "since": body.since.isoformat() if body.since else None, "only": body.only}


@router.get("/admin/collect/status")
def admin_collect_status(x_admin_token: str | None = Header(default=None), token: str | None = Query(default=None)):
    """브라우저에서는 ?token=<ADMIN_TOKEN> 으로 열 수 있다."""
    _check_admin(x_admin_token or token)
    return collect.status()


@router.get("/admin/collect/run")
def admin_collect_run_get(token: str | None = Query(default=None), since: date | None = None, only: str | None = None):
    """브라우저 주소창에서 수집을 시작하는 편의 엔드포인트: /api/admin/collect/run?token=…&since=2015-01-01&only=krx_prices"""
    _check_admin(token)
    names = [n.strip() for n in only.split(",")] if only else None
    if not collect.start_background(since, names):
        raise HTTPException(409, "이미 수집이 진행 중입니다")
    return {"started": True, "since": since.isoformat() if since else None, "only": names,
            "status_url": f"/api/admin/collect/status?token={token}"}


# ------------------------------------------------------------------ 데이터 관리 (S7): 시리즈·이벤트·수집 현황

@router.get("/data/status")
def data_status(s: Session = Depends(get_session)):
    """시리즈별 출처·기간·건수·실데이터 여부, 이벤트 소스별 건수, 마지막 수집 결과. 토큰 불필요(읽기 전용)."""
    from ..engine.catalog import FACTOR_BY_ID as _F  # noqa: PLC0415

    rows = s.execute(
        select(Series.series_id, Series.name, Series.source, Series.unit, Series.license, Series.source_url,
               func.count(SeriesValue.id), func.min(SeriesValue.date), func.max(SeriesValue.date), func.max(SeriesValue.collected_at))
        .outerjoin(SeriesValue, SeriesValue.series_id == Series.series_id)
        .group_by(Series.series_id).order_by(Series.series_id)
    ).all()
    used = {h.pricing.get("series_id") or h.pricing.get("yield_series") for h in s.scalars(select(Holding))} | {f.series_id for f in _F.values()}
    series = []
    for sid, name, source, unit, lic, url, n, d0, d1, collected in rows:
        series.append({
            "series_id": sid, "name": name, "source": source, "unit": unit, "license": lic, "source_url": url,
            "count": n, "first_date": d0.isoformat() if d0 else None, "last_date": d1.isoformat() if d1 else None,
            "collected_at": collected.isoformat() if collected else None,
            "synthetic": source.startswith("SYNTHETIC"), "in_use": sid in used,
            "role": "factor" if sid in _F else ("asset" if sid in used else "other"),
            "factor_name": _F[sid].name if sid in _F else None,
        })
    ev_rows = s.execute(select(PolicyEvent.source, PolicyEvent.is_demo, func.count(), func.min(PolicyEvent.announced_at),
                               func.max(PolicyEvent.announced_at)).group_by(PolicyEvent.source, PolicyEvent.is_demo)).all()
    events = [{"source": src, "is_demo": demo, "count": c, "first_date": d0.isoformat() if d0 else None,
               "last_date": d1.isoformat() if d1 else None} for src, demo, c, d0, d1 in ev_rows]
    from ..collect import status as collect_status  # noqa: PLC0415
    from collectors import run_all  # noqa: PLC0415

    collectors = [{"name": c.name, "description": c.description, "required_key": run_all.ENV_NAMES.get(c.required_key or "", None) if c.required_key else None,
                   "key_present": run_all.key_missing(c, settings) is None} for c in run_all.REGISTRY]
    return {
        "llm_mode": settings.llm_mode, "model_default": settings.model_default, "model_impact_mapper": settings.model_impact_mapper,
        "synthetic_remaining": [x["series_id"] for x in series if x["synthetic"] and x["in_use"]],
        "series": series, "events": events, "collectors": collectors,
        "collect": collect_status(), "admin_enabled": bool(settings.admin_token),
        "daily_hour_utc": settings.collect_daily_hour_utc,
    }
