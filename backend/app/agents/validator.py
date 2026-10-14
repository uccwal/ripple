"""Validator: 규칙 검사. 실패 항목별로 담당 Agent에 반려한다.

규칙
 R1 경로 근거: high/mid 단계는 근거가 있어야 한다. 근거 없는 high → Impact Mapper 반려.
 R2 경로 형식: 경로 ≤3, 단계 ≤4, macro 노드는 유효한 팩터.
 R3 수치 일관성: 자산 기여 합 = 포트폴리오 손익, 범위가 추정치를 포함, 충격값이 calc_log 입력과 일치.
 R4 보고서 인용: 보고서의 모든 숫자가 calc_log.outputs 키에서 왔는지 (Report Writer 단계에서 다시 검사).
 W1 경고: low 단계 존재(근거 불충분), 과거 최대 변동폭 초과, 합성 데이터 사용.
"""
from __future__ import annotations

import math
import re

from ..engine.catalog import FACTOR_BY_ID
from ..models.state import RunState

NUM_RE = re.compile(r"(?<![{\w.])[+\-−]?\d[\d,]*(?:\.\d+)?(?![\w}])")


def check(state: RunState, synthetic: bool) -> dict:
    issues: list[dict] = []
    graph = state.get("graph")
    paths = state.get("impact_paths") or []

    if state["entry"] == "event" and graph:
        if len(paths) > 3 or any(len(p["steps"]) > 4 for p in paths):
            issues.append(_err("path_shape", "Impact Mapper", "경로 수 또는 단계 수가 상한(3개·4단계)을 넘습니다"))
        valid_nodes = {n["id"] for n in graph["nodes"]}
        for n in graph["nodes"]:
            if n["layer"] == "macro" and n.get("factor_id") not in FACTOR_BY_ID:
                issues.append(_err("macro_factor", "Impact Mapper", f"거시 변수 노드 '{n['label']}'가 팩터에 대응되지 않습니다"))
        for p in paths:
            for s in p["steps"]:
                if s["from"] not in valid_nodes or s["to"] not in valid_nodes:
                    issues.append(_err("dangling_edge", "Impact Mapper", f"존재하지 않는 노드를 잇는 단계: {s['from']}→{s['to']}"))
                if s["confidence"] == "high" and len(s.get("evidence", [])) < 2:
                    issues.append(_err("high_without_evidence", "Impact Mapper",
                                       f"확신도 high 단계({s['from']}→{s['to']})의 정량 근거가 2건 미만입니다"))
                if s["confidence"] == "mid" and not s.get("evidence"):
                    issues.append(_err("mid_without_evidence", "Impact Mapper",
                                       f"확신도 mid 단계({s['from']}→{s['to']})에 근거가 없습니다"))
        low = [s for p in paths for s in p["steps"] if s["confidence"] == "low"]
        if low:
            issues.append(_warn("low_evidence", "Impact Mapper", f"근거 불충분(low) 단계 {len(low)}개 — 결과 해석 시 주의"))
        factor_nodes = {n["factor_id"] for n in graph["nodes"] if n.get("factor_id")}
        shock_vars = {s["variable"] for s in (state.get("scenario") or {}).get("shocks", [])}
        extra = shock_vars - factor_nodes
        if extra:
            issues.append(_err("shock_not_in_path", "Scenario Builder", f"경로에 없는 팩터에 충격이 들어갔습니다: {', '.join(sorted(extra))}"))

    scenario = state.get("scenario") or {}
    over = [s["variable"] for s in scenario.get("shocks", []) if s.get("over_hist")]
    if over:
        issues.append(_warn("over_hist", "Scenario Builder", f"과거 최대 변동폭 초과: {', '.join(over)}"))

    result = state.get("result")
    calc = state.get("calc_log")
    if result and calc:
        total = sum(a["contribution"] for a in result["by_asset"])
        if abs(total - result["portfolio_pnl"]) > 1e-6:
            issues.append(_err("sum_mismatch", "Risk Engine", "자산 기여 합이 포트폴리오 손익과 다릅니다"))
        if not (result["range"]["low"] - 1e-9 <= result["portfolio_pnl"] <= result["range"]["high"] + 1e-9):
            issues.append(_err("range_mismatch", "Risk Engine", "추정 범위가 추정치를 포함하지 않습니다"))
        in_shocks = calc["inputs"]["shocks"]
        for s in scenario.get("shocks", []):
            if abs(in_shocks.get(s["variable"], float("nan")) - s["change"]) > 1e-9:
                issues.append(_err("shock_mismatch", "Risk Engine", f"계산 입력 충격값이 시나리오와 다릅니다: {s['variable']}"))
        if any(math.isnan(a["ret"]) for a in result["by_asset"]):
            issues.append(_err("nan_result", "Risk Engine", "자산 수익률에 NaN이 있습니다"))
    elif state.get("result") is None:
        issues.append(_err("no_result", "Risk Engine", "계산 결과가 없습니다"))

    if synthetic:
        issues.append(_warn("synthetic_data", "Risk Engine", "합성 시계열로 계산한 데모 결과입니다 (실제 시장 데이터 아님)"))
    if (state.get("event") or {}).get("missing_fields"):
        issues.append(_warn("event_missing", "Event Analyst", "이벤트 필수 필드 일부를 원문에서 확인하지 못했습니다"))

    errors = [i for i in issues if i["severity"] == "error"]
    rules_total = 4
    rules_failed = len({i["code"].split("_")[0] for i in errors})
    return {
        "passed": not errors,
        "status": "fail" if errors else ("warn" if issues else "pass"),
        "rules_total": rules_total,
        "rules_passed": max(rules_total - min(rules_failed, rules_total), 0),
        "issues": issues,
    }


def check_report(markdown: str, outputs: dict, horizon: int, allowed: list[str] | None = None) -> list[str]:
    """R4: 보고서 본문의 숫자가 모두 calc_log.outputs에서 치환된 것인지 확인한다. 반환: 위반 목록."""
    # 치환된 숫자는 <!--k:KEY-->…<!--/k--> 마커로 감싸져 있다. 마커 밖의 숫자를 찾는다.
    stripped = re.sub(r"<!--k:[^>]*-->.*?<!--/k-->", "", markdown, flags=re.S)
    for lit in allowed or []:
        if lit:
            stripped = stripped.replace(lit, "")  # 사용자 입력 원문 등 허용 리터럴
    stripped = re.sub(r"^\[\d+\] .*$", "", stripped, flags=re.M)  # 출처 목록 (수집일·라이선스 문구)
    stripped = re.sub(r"^#+ .*$", "", stripped, flags=re.M)  # 제목 번호
    stripped = re.sub(r"^\d+\. ", "", stripped, flags=re.M)  # 목록 번호
    stripped = re.sub(r"\d{4}-\d{2}-\d{2}", "", stripped)  # 날짜
    stripped = re.sub(r"`[^`]*`", "", stripped)              # 코드(계산 ID)
    stripped = re.sub(r"^계산 코드 해시.*$", "", stripped, flags=re.M)
    stripped = re.sub(r"\|.*\|", "", stripped)             # 표(계산 로그에서 직접 생성)
    stripped = re.sub(r"R²\s*\S+", "", stripped)
    bad = [m.group(0) for m in NUM_RE.finditer(stripped)]
    return [f"출처 없는 수치 '{b}'" for b in bad]


def _err(code: str, agent: str, msg: str) -> dict:
    return {"code": code, "severity": "error", "agent": agent, "message": msg}


def _warn(code: str, agent: str, msg: str) -> dict:
    return {"code": code, "severity": "warn", "agent": agent, "message": msg}
