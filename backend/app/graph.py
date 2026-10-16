"""LangGraph 상태 그래프. 노드 = Agent, 엣지 = 설계서 2장 실행 흐름.

event 입구:    event_analyst → impact_mapper → scenario_builder → regime_finder → risk_engine → validator → report_writer
scenario 입구: scenario_builder부터
재계산(PATCH): regime_finder부터 (이전 실행의 event·경로·시나리오 재사용)
Validator가 반려하면 담당 Agent로 되돌아간다 (Impact Mapper 최대 2회, Risk Engine 최대 1회).
"""
from __future__ import annotations

import json
import logging
import math
import traceback
import uuid
from datetime import date, datetime
from typing import Literal

from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import runner
from .agents import event_analyst, impact_mapper, report_writer, scenario_builder, validator
from .config import settings
from .db import SessionLocal
from .engine import outcome, risk
from .engine.catalog import FACTOR_BY_ID
from .llm import LLMError
from .util import utcnow
from .models.state import AGENTS, RunState
from .models.tables import CalcLog, Holding, PolicyEvent, Portfolio, Run

log = logging.getLogger(__name__)
ORDER = ["event_analyst", "impact_mapper", "scenario_builder", "regime_finder", "risk_engine", "validator", "report_writer"]
NODE_AGENT = dict(zip(ORDER, AGENTS))


class RunContext:
    """그래프 실행 1회의 DB 세션·로그·엔진 컨텍스트 (LangGraph 상태에는 직렬화 가능한 값만 둔다)."""

    def __init__(self, session: Session, run_id: str, entry: str):
        self.session = session
        self.run_id = run_id
        self.steps = runner.StepLogger(session, run_id, entry)
        self.engine_ctx: risk.Context | None = None
        self.stats: dict | None = None
        self.regimes: list = []
        self.rejected_issues: list[str] = []

    def engine(self, state: RunState) -> risk.Context:
        if self.engine_ctx is None:
            as_of = date.fromisoformat(state["as_of"]) if state.get("as_of") else None
            self.engine_ctx = risk.prepare(self.session, state["portfolio_id"], as_of, state["horizon_days"])
            self.stats = risk.scenario_stats(self.engine_ctx)
        return self.engine_ctx

    def holdings_summary(self) -> list[dict]:
        return [{"name": h.name, "asset_class": h.asset_class, "currency": h.currency, "sector": h.sector, "weight": h.weight}
                for h in self.engine_ctx.holdings]


def build(rc: RunContext):
    g = StateGraph(RunState)

    def node_event_analyst(state: RunState) -> dict:
        ev = rc.session.get(PolicyEvent, state["event"]["event_id"])
        step = rc.steps.start("Event Analyst", {"summary": f"{ev.source} 원문 ({ev.announced_at})"})
        try:
            event, meta = event_analyst.run(state, ev)
        except Exception as e:
            rc.steps.fail(step, str(e))
            raise
        rc.steps.finish(step, {"summary": meta["summary"]}, meta["model"], meta["tokens"], meta.get("note", ""))
        head = event["title"] if event["title"].startswith(event["country_name"]) else f"{event['country_name']} {event['title']}"
        vt = event.get("value_text") or ""
        core = vt.split(" (")[0].strip()  # "+0.25%p (2.75%→3.00%)" → "+0.25%p"
        dup = not vt or vt in head or (core and core.replace("−", "-") in head.replace("−", "-"))
        return {"event": event, "title": head if dup else f"{head} ({vt})"}

    def node_impact_mapper(state: RunState) -> dict:
        attempt = state.get("retries", {}).get("impact", 0) + 1
        step = rc.steps.start("Impact Mapper", {"summary": "event + 과거 사례·거시 요약 통계" + (f" · 반려 사유 {len(rc.rejected_issues)}건 반영" if rc.rejected_issues else "")})
        try:
            rc.engine(state)
            paths, graph, meta = impact_mapper.run(state, rc.stats, rc.holdings_summary(), rc.rejected_issues or None)
        except Exception as e:
            rc.steps.fail(step, str(e))
            raise
        rc.steps.finish(step, {"summary": meta["summary"]}, meta["model"], meta["tokens"],
                        f"{attempt}차 추론" if attempt > 1 else "")
        return {"impact_paths": paths, "graph": graph}

    def node_scenario_builder(state: RunState) -> dict:
        step = rc.steps.start("Scenario Builder", {"summary": f"impact_paths {len(state.get('impact_paths') or [])}개" if state["entry"] == "event" else f"자연어: {state['input_text']}"})
        try:
            rc.engine(state)
            scenario, meta = scenario_builder.run(state, rc.stats)
        except Exception as e:
            rc.steps.fail(step, str(e))
            raise
        rc.steps.finish(step, {"summary": meta["summary"]}, meta["model"], meta["tokens"], meta.get("note", ""))
        title = state.get("title") or state["input_text"]
        return {"scenario": scenario, "title": title}

    def node_regime_finder(state: RunState) -> dict:
        step = rc.steps.start("Regime Finder", {"summary": f"scenario ({state['horizon_days']}영업일) · 충격 {len(state['scenario']['shocks'])}개"})
        try:
            ctx = rc.engine(state)
            shocks = {s["variable"]: s["change"] for s in state["scenario"]["shocks"]}
            rc.regimes = risk.find_regimes(ctx, shocks)
        except Exception as e:
            rc.steps.fail(step, str(e))
            raise
        top = max((r.similarity for r in rc.regimes), default=0.0)
        rc.steps.finish(step, {"summary": f"유사 구간 {len(rc.regimes)}개 · 최고 {top:.2f}" if rc.regimes else "유사 구간 없음 · 팩터 모델만 사용"},
                        "engine (LLM 없음)")
        regimes = [{"start": r.start.date().isoformat(), "end": r.end.date().isoformat(), "similarity": r.similarity,
                    "tag": r.tag, "pnl": None if math.isnan(r.pnl) else r.pnl, "factor_changes": r.factor_changes}
                   for r in rc.regimes]
        return {"regimes": regimes}

    def node_risk_engine(state: RunState) -> dict:
        ctx = rc.engine(state)
        step = rc.steps.start("Risk Engine", {"summary": f"scenario · 포트폴리오 {len(ctx.holdings)}종목 · 유사 국면 {len(rc.regimes)}개"})
        try:
            shocks = {s["variable"]: s["change"] for s in state["scenario"]["shocks"]}
            out = risk.compute(ctx, shocks, rc.regimes, state["run_id"])
            # 사후 검증(발표일이 과거면 실제 움직임과 비교) · 다른 포트폴리오 비교 — 모두 엔진 계산
            ev = state.get("event") or {}
            actual = None
            if ev.get("announced_at"):
                try:
                    actual = outcome.actual_outcome(rc.session, ctx.holdings, date.fromisoformat(ev["announced_at"]),
                                                    ctx.horizon, shocks, out["result"]["portfolio_pnl"])
                except Exception as e:  # noqa: BLE001  사후 검증은 보조 정보라 실패해도 분석을 멈추지 않는다
                    log.warning("사후 검증 계산 실패: %s", e)
            cross = outcome.cross_portfolio(rc.session, ctx.portfolio.portfolio_id, ctx.as_of, ctx.horizon, shocks, state["run_id"])
            risk.attach_extras(out, ctx, actual, cross)
        except Exception as e:
            rc.steps.fail(step, str(e))
            raise
        calc = out["calc_log"]
        rc.session.add(CalcLog(calc_id=calc["calc_id"], run_id=state["run_id"], code_hash=calc["code_hash"],
                               engine_version=calc["engine_version"], inputs=calc["inputs"],
                               outputs={"outputs": calc["outputs"], "entries": calc["entries"]}))
        rc.session.commit()
        from .engine import fmt
        extra = []
        if actual and actual.get("portfolio_pnl") is not None:
            extra.append(f"실제 {fmt.signed(actual['portfolio_pnl'])}" + ("" if actual["complete"] else " (잠정)"))
        if len(out["result"]["cross_portfolio"]) > 1:
            extra.append(f"포트폴리오 {len(out['result']['cross_portfolio'])}개 비교")
        rc.steps.finish(step, {"summary": f"ΔP {fmt.signed(out['result']['portfolio_pnl'])} · {calc['calc_id']}"}, "engine (LLM 없음)",
                        note=" · ".join(extra))
        return {"result": out["result"], "calc_log": calc}

    def node_validator(state: RunState) -> dict:
        step = rc.steps.start("Validator", {"summary": "RunState · 계산 로그 대조"})
        v = validator.check(state, rc.engine(state).synthetic)
        errors = [i for i in v["issues"] if i["severity"] == "error"]
        retries = dict(state.get("retries", {}))
        rejections = list(state.get("rejections", []))
        if errors:
            target = errors[0]["agent"]
            key = {"Impact Mapper": "impact", "Risk Engine": "risk", "Scenario Builder": "impact"}.get(target, "impact")
            limit = settings.max_retry_impact if key == "impact" else settings.max_retry_risk
            if retries.get(key, 0) < limit:
                retries[key] = retries.get(key, 0) + 1
                issues = [i["message"] for i in errors if i["agent"] == target]
                rc.rejected_issues = issues
                rejections.append({"to": target, "issues": issues})
                rc.steps.retry(step, target if target != "Scenario Builder" else "Impact Mapper", issues)
                return {"validation": v, "retries": retries, "rejections": rejections, "_reject_to": target}
            # 상한 초과: 부분 결과 + 경고로 종료
            v["issues"].append({"code": "retry_exhausted", "severity": "warn", "agent": "Orchestrator",
                                "message": f"{target} 재시도 상한({limit}회) 초과 — 부분 결과로 종료"})
            v["status"] = "warn"
            rc.steps.finish(step, {"summary": f"규칙 {v['rules_passed']}/{v['rules_total']} · 재시도 상한 초과", "issues": v["issues"]},
                            "규칙 (LLM 없음)", note="재시도 상한 초과 · 부분 결과")
            return {"validation": v, "retries": retries, "rejections": rejections, "partial": True, "_reject_to": None}
        rc.rejected_issues = []
        warns = [i["message"] for i in v["issues"]]
        note = ("경고: " + "; ".join(warns)) if warns else "검증 통과 · 규칙 4/4"
        if rejections:
            note = f"{len(rejections)}차 반려 후 통과 · 규칙 {v['rules_passed']}/{v['rules_total']}" + (f" · 경고 {len(warns)}건" if warns else "")
        rc.steps.finish(step, {"summary": f"규칙 {v['rules_passed']}/{v['rules_total']} 통과", "issues": v["issues"]}, "규칙 (LLM 없음)", note=note)
        return {"validation": v, "retries": retries, "rejections": rejections, "_reject_to": None}

    def node_report_writer(state: RunState) -> dict:
        allowed = _allowed_literals(state)
        outputs = dict(state["calc_log"]["outputs"])
        outputs.update(report_writer.extra_outputs(state))
        rejected: list[str] = []
        report = meta = None
        bad: list[str] = []
        for attempt in (1, 2):
            step = rc.steps.start("Report Writer", {"summary": "RunState 전체 · 수치 키 목록" + (f" · 반려 사유 {len(rejected)}건" if rejected else "")})
            try:
                report, meta = report_writer.run(state, rejected or None)
            except Exception as e:
                rc.steps.fail(step, str(e))
                raise
            # R4: 보고서 수치 인용 검사. 위반이 있으면 사유를 주고 한 번 다시 쓰게 한다 (LLM 모드에서만 의미 있음)
            bad = validator.check_report(report["markdown"], outputs, state["horizon_days"], allowed) + \
                  [f"알 수 없는 수치 키 '{k}'" for k in meta.get("unknown_keys", [])]
            if not bad or attempt == 2 or meta["model"] == "offline 규칙":
                break
            rc.steps.finish(step, {"summary": meta["summary"]}, meta["model"], meta["tokens"],
                            f"수치 인용 검사 실패 {len(bad)}건 → 재작성")
            rejected = bad
        v = dict(state["validation"])
        if bad:
            v = {**v, "issues": v["issues"] + [{"code": "report_uncited", "severity": "warn", "agent": "Report Writer",
                                                "message": "보고서에 계산 로그와 연결되지 않은 수치가 있어 해당 문장을 제거했습니다: " + ", ".join(bad[:5])}]}
            v["status"] = "warn" if v["status"] == "pass" else v["status"]
            report["markdown"] = _drop_uncited(report["markdown"], allowed)
        rc.steps.finish(step, {"summary": meta["summary"]}, meta["model"], meta["tokens"],
                        ("수치 인용 검사: 미인용 수치 제거 " + str(len(bad)) + "건") if bad else
                        ("재작성 후 수치 인용 검사 통과" if rejected else "수치 인용 검사 통과"))
        return {"report": report, "validation": v}

    for name, fn in [("event_analyst", node_event_analyst), ("impact_mapper", node_impact_mapper),
                     ("scenario_builder", node_scenario_builder), ("regime_finder", node_regime_finder),
                     ("risk_engine", node_risk_engine), ("validator", node_validator), ("report_writer", node_report_writer)]:
        g.add_node(name, fn)

    def entry_router(state: RunState) -> str:
        if state.get("resume_from"):
            return state["resume_from"]
        return "event_analyst" if state["entry"] == "event" else "scenario_builder"

    g.set_conditional_entry_point(entry_router, {n: n for n in ORDER})
    g.add_edge("event_analyst", "impact_mapper")
    g.add_edge("impact_mapper", "scenario_builder")
    g.add_edge("scenario_builder", "regime_finder")
    g.add_edge("regime_finder", "risk_engine")
    g.add_edge("risk_engine", "validator")

    def after_validator(state: RunState) -> Literal["impact_mapper", "regime_finder", "report_writer"]:
        target = state.get("_reject_to")
        if target in ("Impact Mapper", "Scenario Builder"):
            return "impact_mapper"
        if target == "Risk Engine":
            return "regime_finder"
        return "report_writer"

    g.add_conditional_edges("validator", after_validator, {"impact_mapper": "impact_mapper", "regime_finder": "regime_finder", "report_writer": "report_writer"})
    g.add_edge("report_writer", END)
    return g.compile()


def _allowed_literals(state: RunState) -> list[str]:
    """보고서 수치 검사에서 허용하는 리터럴: 사용자 입력, 이벤트 제목·핵심 수치, 노드 라벨, 자산·팩터 이름."""
    ev = state.get("event") or {}
    out = [state.get("input_text", ""), ev.get("title", ""), ev.get("value_text", ""), ev.get("announced_at", "")]
    out += [n["label"] for n in (state.get("graph") or {}).get("nodes", [])]
    out += [a["name"] for a in (state.get("result") or {}).get("by_asset", [])]
    out += [f.name for f in FACTOR_BY_ID.values()]
    out += [h["title"] for h in (state.get("result") or {}).get("hedges", [])]
    return sorted({x for x in out if x}, key=len, reverse=True)


def _drop_uncited(md: str, allowed: list[str] = ()) -> str:
    """미인용 숫자가 든 문장(마커 밖)을 제거한다. 표·제목·출처 줄은 유지."""
    import re
    def clean_line(x: str) -> str:
        for lit in allowed:
            if lit:
                x = x.replace(lit, "")
        return re.sub(r"<!--k:[^>]*-->.*?<!--/k-->|\d{4}-\d{2}-\d{2}|`[^`]*`|\[\d+\]", "", x)

    out = []
    for line in md.split("\n"):
        if line.startswith(("#", "|", "[", "-", "계산 코드")) or not line.strip():
            out.append(line)
            continue
        stripped = clean_line(line)
        prefix = re.match(r"^\d+\. ", line)
        body = line[prefix.end():] if prefix else line
        sentences = re.split(r"(?<=[.다])\s+", body)
        def clean(x: str) -> str:
            for lit in allowed:
                if lit:
                    x = x.replace(lit, "")
            return re.sub(r"<!--k:[^>]*-->.*?<!--/k-->|\d{4}-\d{2}-\d{2}|`[^`]*`", "", x)
        kept = [s for s in sentences if not validator.NUM_RE.search(clean(s))]
        out.append(((prefix.group(0) if prefix else "") + " ".join(kept)) if re.search(r"\d", stripped) else line)
    return "\n".join(out)


# ---------------------------------------------------------------- 실행 진입점 (백그라운드 스레드)

def serializable(state: RunState) -> dict:
    return {k: v for k, v in state.items() if not k.startswith("_")}


def execute(run_id: str) -> None:
    session = SessionLocal()
    run = session.get(Run, run_id)
    last: dict = dict(run.state)
    try:
        run.status = "running"
        session.commit()
        runner.mark_running(run_id)
        rc = RunContext(session, run_id, run.entry)
        state: RunState = dict(run.state)  # type: ignore[assignment]
        state.setdefault("retries", {})
        state.setdefault("rejections", [])
        # 입구별 건너뛰기·재사용 표시
        if run.entry == "scenario" and not state.get("resume_from"):
            rc.steps.skip("Event Analyst", "시나리오 직접 입력 — 해당 없음")
            rc.steps.skip("Impact Mapper", "시나리오 직접 입력 — 해당 없음")
        if state.get("resume_from") == "regime_finder":
            for agent, key in (("Event Analyst", "event"), ("Impact Mapper", "impact_paths"), ("Scenario Builder", "scenario")):
                if state.get(key):
                    rc.steps.reuse(agent, {"summary": "이전 실행 결과 재사용 (충격값 수정)"})
                else:
                    rc.steps.skip(agent, "시나리오 직접 입력 — 해당 없음")
        app = build(rc)
        last = state
        # stream_mode="values": 노드가 끝날 때마다 전체 상태를 받는다 → 실패해도 부분 결과를 남길 수 있다
        for last in app.stream(state, config={"recursion_limit": 40}, stream_mode="values"):
            pass
        run.state = serializable(last)
        run.title = last.get("title") or run.title
        run.status = "partial" if last.get("partial") else "done"
    except (LLMError, ValueError) as e:
        log.warning("run %s failed: %s", run_id, e)
        session.rollback()
        run.status = "failed"
        run.error = str(e)
        run.state = serializable(last)
    except Exception as e:  # noqa: BLE001
        log.error("run %s crashed: %s\n%s", run_id, e, traceback.format_exc())
        session.rollback()
        run.status = "failed"
        run.error = f"내부 오류: {type(e).__name__}: {e}"
        run.state = serializable(last)
    finally:
        try:
            run = session.merge(run)
            run.finished_at = utcnow()
            session.commit()
        except Exception as e:  # noqa: BLE001
            log.error("run %s: 종료 상태 저장 실패: %s", run_id, e)
            session.rollback()
        runner.mark_done(run_id)
        timeline = runner.build_timeline(session, run)
        runner.publish(run_id, "run_finished", {"run_id": run_id, "status": run.status, "error": run.error,
                                                "elapsed_ms": runner.elapsed_ms(run), "current": None, "step": None,
                                                "steps": timeline, "retry_loops": runner.retry_loops(session, run)})
        session.close()


def create_run(session: Session, entry: str, portfolio_id: str, event_id: str | None, scenario_text: str | None,
               horizon_days: int, as_of: date | None = None, parent: Run | None = None,
               shock_overrides: dict[str, float] | None = None) -> Run:
    if session.get(Portfolio, portfolio_id) is None:
        raise ValueError(f"포트폴리오 없음: {portfolio_id}")
    run_id = "run_" + uuid.uuid4().hex[:12]
    state: RunState = {
        "run_id": run_id, "parent_run_id": parent.run_id if parent else None, "entry": entry,
        "input_text": scenario_text or "", "portfolio_id": portfolio_id, "horizon_days": horizon_days,
        "as_of": as_of.isoformat() if as_of else None, "title": "", "event": None, "impact_paths": [], "graph": None,
        "scenario": None, "regimes": [], "result": None, "calc_log": None, "validation": None, "report": None,
        "retries": {}, "rejections": [], "resume_from": None, "partial": False, "error": None,
    }
    title = scenario_text or ""
    if entry == "event" and parent is None:
        ev = session.get(PolicyEvent, event_id)
        if ev is None:
            raise ValueError(f"이벤트 없음: {event_id}")
        state["event"] = {"event_id": ev.event_id, "country": ev.country, "type": ev.type, "title": ev.title}
        title = ev.title
    if parent is not None:
        ps = parent.state
        state.update({"entry": ps["entry"], "input_text": ps["input_text"], "event": ps.get("event"),
                      "impact_paths": ps.get("impact_paths", []), "graph": ps.get("graph"), "title": ps.get("title", ""),
                      "resume_from": "regime_finder"})
        scenario = json.loads(json.dumps(ps["scenario"]))
        present = {s["variable"] for s in scenario["shocks"]}
        for var in (shock_overrides or {}):
            if var not in present and var in FACTOR_BY_ID:  # 새 변수 추가
                scenario["shocks"].append({"variable": var, "name": FACTOR_BY_ID[var].name, "change": 0.0,
                                           "unit": FACTOR_BY_ID[var].unit, "basis": "사용자 추가값", "hist_max": None,
                                           "hist_pct": None, "over_hist": False})
        for s in scenario["shocks"]:
            if s["variable"] in (shock_overrides or {}):
                s["change"] = float(shock_overrides[s["variable"]])
                s["basis"] = "사용자 수정값"
                hm = s.get("hist_max")
                s["hist_pct"] = round(abs(s["change"]) / hm * 100, 1) if hm else None
                s["over_hist"] = bool(hm and abs(s["change"]) > hm)
        state["scenario"] = scenario
        title = ps.get("title", "")
    run = Run(run_id=run_id, parent_run_id=state["parent_run_id"], entry=state["entry"], input_text=state["input_text"],
              event_id=event_id or (parent.event_id if parent else None), portfolio_id=portfolio_id,
              horizon_days=horizon_days, as_of=as_of, status="queued", title=title, llm_mode=settings.llm_mode, state=state)
    session.add(run)
    session.commit()
    return run
