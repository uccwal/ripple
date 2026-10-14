"""실행 관리: 단계 로그(agent_step), SSE 이벤트 버스, 타임라인 조립."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .util import utcnow
from .models.state import AGENT_DESC, AGENTS
from .models.tables import AgentStep, Run

_loop: asyncio.AbstractEventLoop | None = None
_subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
_lock = threading.Lock()
_running: dict[str, float] = {}  # run_id → 시작 시각(perf)


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    with _lock:
        _subs[run_id].append(q)
    return q


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    with _lock:
        if q in _subs.get(run_id, []):
            _subs[run_id].remove(q)
        if run_id in _subs and not _subs[run_id]:
            del _subs[run_id]


def publish(run_id: str, event: str, data: dict) -> None:
    """워커 스레드에서 호출. 이벤트 루프로 안전하게 넘긴다."""
    if _loop is None:
        return
    payload = {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}
    with _lock:
        queues = list(_subs.get(run_id, []))
    for q in queues:
        _loop.call_soon_threadsafe(q.put_nowait, payload)


def mark_running(run_id: str) -> None:
    _running[run_id] = time.perf_counter()


def mark_done(run_id: str) -> None:
    _running.pop(run_id, None)


def elapsed_ms(run: Run) -> int:
    if run.run_id in _running:
        return int((time.perf_counter() - _running[run.run_id]) * 1000)
    if run.finished_at and run.created_at:
        return int((run.finished_at - run.created_at).total_seconds() * 1000)
    return 0


# ------------------------------------------------------------------ 단계 로그

class StepLogger:
    """Agent 한 단계의 시작·종료를 agent_step에 남기고 SSE로 알린다."""

    def __init__(self, session: Session, run_id: str, entry: str):
        self.session = session
        self.run_id = run_id
        self.entry = entry
        self.attempts: dict[str, int] = defaultdict(int)

    def skip(self, agent: str, note: str = "") -> None:
        self.session.add(AgentStep(run_id=self.run_id, agent=agent, attempt=1, status="skip", note=note,
                                   started_at=utcnow(), ended_at=utcnow()))
        self.session.commit()

    def reuse(self, agent: str, output: dict, note: str = "이전 실행 결과 재사용") -> None:
        now = utcnow()
        self.session.add(AgentStep(run_id=self.run_id, agent=agent, attempt=1, status="done", note=note,
                                   output=output, model="재사용", started_at=now, ended_at=now))
        self.session.commit()

    def start(self, agent: str, input_summary: dict) -> AgentStep:
        self.attempts[agent] += 1
        step = AgentStep(run_id=self.run_id, agent=agent, attempt=self.attempts[agent], status="running",
                         input=input_summary, started_at=utcnow())
        self.session.add(step)
        self.session.commit()
        self._emit("step_started", step)
        return step

    def finish(self, step: AgentStep, output: dict, model: str = "", tokens: tuple[int, int] = (0, 0),
               note: str = "") -> None:
        step.status = "done"
        step.output = output
        step.model = model
        step.tokens_in, step.tokens_out = tokens
        step.note = note
        step.ended_at = utcnow()
        self.session.commit()
        self._emit("step_finished", step)

    def fail(self, step: AgentStep, error: str, model: str = "", tokens: tuple[int, int] = (0, 0)) -> None:
        step.status = "failed"
        step.note = error
        step.model = model
        step.tokens_in, step.tokens_out = tokens
        step.ended_at = utcnow()
        self.session.commit()
        self._emit("step_failed", step)

    def retry(self, validator_step: AgentStep, target_agent: str, issues: list[str]) -> None:
        """Validator가 target_agent에 반려. Validator 단계는 done(반려)로 닫고 대상은 retry 상태로 알린다."""
        validator_step.status = "done"
        validator_step.note = f"반려 → {target_agent}: " + "; ".join(issues)[:300]
        validator_step.output = {"passed": False, "rejected_to": target_agent, "issues": issues}
        validator_step.model = "규칙 (LLM 없음)"
        validator_step.ended_at = utcnow()
        # 대상 Agent에 retry 마커 (타임라인 표시용)
        marker = AgentStep(run_id=self.run_id, agent=target_agent, attempt=self.attempts[target_agent],
                           status="retry", note="Validator 반려 · 재실행 대기", started_at=utcnow(),
                           ended_at=utcnow())
        self.session.add(marker)
        self.session.commit()
        self._emit("step_retry", marker)

    def _emit(self, event: str, step: AgentStep) -> None:
        run = self.session.get(Run, self.run_id)
        timeline = build_timeline(self.session, run)
        current = next((f"{s['agent']} — {s['desc']}" + (f" ({s['attempt']}차 시도)" if s["attempt"] > 1 else "")
                        for s in timeline if s["status"] == "running"), None)
        publish(self.run_id, event, {
            "run_id": self.run_id, "status": run.status, "elapsed_ms": elapsed_ms(run), "current": current,
            "step": step_view(step, run), "steps": timeline, "retry_loops": retry_loops(self.session, run),
        })


# ------------------------------------------------------------------ 타임라인 조립

def _fmt_tokens(s: AgentStep) -> str:
    return f"{s.tokens_in:,} / {s.tokens_out:,}" if (s.tokens_in or s.tokens_out) else "—"


def step_view(s: AgentStep, run: Run) -> dict:
    idx = AGENTS.index(s.agent)
    status = s.status
    if status == "running" and run.status in ("failed",):
        status = "failed"
    return {
        "idx": idx, "agent": s.agent, "desc": AGENT_DESC[s.agent], "status": status, "attempt": s.attempt,
        "elapsed_ms": int((s.ended_at - s.started_at).total_seconds() * 1000) if s.ended_at else None,
        "note": s.note or "",
        "input_summary": _summ(s.input), "output_summary": _summ(s.output),
        "model": s.model or ("engine (LLM 없음)" if s.agent in ("Regime Finder", "Risk Engine")
                             else "규칙 (LLM 없음)" if s.agent == "Validator" else ""),
        "tokens": _fmt_tokens(s),
    }


def _summ(d: dict | None) -> str:
    if not d:
        return ""
    if "summary" in d and isinstance(d["summary"], str):
        return d["summary"]
    return json.dumps(d, ensure_ascii=False, default=str)[:160]


def build_timeline(session: Session, run: Run) -> list[dict]:
    steps = list(session.scalars(select(AgentStep).where(AgentStep.run_id == run.run_id).order_by(AgentStep.step_id)))
    latest: dict[str, AgentStep] = {}
    for s in steps:
        prev = latest.get(s.agent)
        # retry 마커는 그 뒤에 실제 재실행(running/done)이 오면 덮어쓴다
        if prev is None or prev.status == "retry" or s.status != "retry" or s.step_id > prev.step_id:
            latest[s.agent] = s
    out = []
    for i, agent in enumerate(AGENTS):
        s = latest.get(agent)
        if s is None:
            out.append({"idx": i, "agent": agent, "desc": AGENT_DESC[agent], "status": "wait", "attempt": 1,
                        "elapsed_ms": None, "note": "", "input_summary": "", "output_summary": "",
                        "model": "", "tokens": "—"})
        else:
            v = step_view(s, run)
            v["attempt"] = max((x.attempt for x in steps if x.agent == agent and x.status != "retry"), default=1)
            out.append(v)
    # 반려 후 재실행 대기 중이면 뒤 단계는 wait로 되돌린다
    if any(v["status"] == "retry" for v in out):
        ri = next(v["idx"] for v in out if v["status"] == "retry")
        for v in out:
            if v["idx"] > ri and v["agent"] != "Validator":
                v["status"] = "wait"
    return out


def retry_loops(session: Session, run: Run) -> list[dict]:
    steps = session.scalars(select(AgentStep).where(AgentStep.run_id == run.run_id, AgentStep.status == "retry"))
    seen = set()
    out = []
    for s in steps:
        key = (AGENTS.index("Validator"), AGENTS.index(s.agent))
        if key not in seen:
            seen.add(key)
            out.append({"from_idx": key[0], "to_idx": key[1]})
    return out
