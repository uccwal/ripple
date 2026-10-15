"""Scenario Builder: impact_paths 또는 자연어 → 팩터별 충격값. 과거 최대 변동폭을 넘으면 경고."""
from __future__ import annotations

import json
import re
from statistics import median

from .. import llm, prompts
from ..config import settings
from ..engine import fmt
from ..engine.catalog import FACTOR_BY_ID, FACTOR_IDS, match_factor
from ..models.state import RunState, ScenarioShocks, ShockItem
from .common import analog_summary_text, factor_list_text, model_label

_NUM = r"([+-]?\d+(?:\.\d+)?)\s*(%p|%|bp|퍼센트포인트|포인트|퍼센트|프로)"


def parse_natural(text: str) -> dict[str, float]:
    """자연어에서 '변수 + 크기 + 방향'을 뽑는다. 예: 유가 30% 급등 + 원화 10% 약세 → {WTI: 30, USDKRW: 10}."""
    out: dict[str, float] = {}
    for chunk in re.split(r"[+,、와과및/]|\s그리고\s", text):
        fid = match_factor(chunk)
        if fid is None:
            continue
        m = re.search(_NUM, chunk)
        if not m:
            continue
        val = float(m.group(1))
        unit = m.group(2)
        if unit == "bp":
            val /= 100
        elif unit in ("%", "퍼센트", "프로") and FACTOR_BY_ID[fid].unit == "%p":
            pass  # 금리 "1%" 는 1%p 로 해석
        neg_words = ["하락", "약세", "급락", "인하", "감소", "절상"] if fid != "USDKRW" else ["하락", "강세", "급락", "절상"]
        pos_words = ["상승", "급등", "인상", "증가", "약세"] if fid == "USDKRW" else ["상승", "급등", "인상", "증가", "강세"]
        if fid == "DXY_BROAD":
            sign = -1 if any(w in chunk for w in ("약세", "하락", "급락")) else 1
        elif fid == "USDKRW":
            # '원화 약세' = 환율 상승, '원화 강세' = 환율 하락, '달러 약세' = 환율 하락
            if "원화" in chunk:
                # '원화 약세/하락/급락' = 원화 가치 하락 = 환율 상승. '원화 강세/절상' 만 환율 하락
                sign = -1 if any(w in chunk for w in ("강세", "절상")) else 1
            elif "달러" in chunk:
                sign = -1 if any(w in chunk for w in ("약세", "하락")) else 1
            else:
                sign = -1 if any(w in chunk for w in ("하락", "급락")) else 1
        else:
            sign = -1 if any(w in chunk for w in neg_words) else 1 if any(w in chunk for w in pos_words) else (1 if val >= 0 else -1)
        out[fid] = sign * abs(val)
    return out


def _offline_from_paths(state: RunState, stats: dict) -> ScenarioShocks:
    graph = state.get("graph") or {}
    directions: dict[str, str] = {}
    for e in graph.get("edges", []):
        tgt = next((n for n in graph["nodes"] if n["id"] == e["target"]), None)
        if tgt and tgt.get("factor_id"):
            # 노드 라벨의 상승/하락으로 방향을 정한다
            directions[tgt["factor_id"]] = "-" if any(w in tgt["label"] for w in ("하락", "감소", "약세")) else "+"
    ev_type = (state.get("event") or {}).get("type", "tariff")
    analogs = stats["analogs"].get(ev_type, [])
    shocks = []
    for fid, d in directions.items():
        vals = [a["changes"][fid] for a in analogs if fid in a["changes"]]
        if vals:
            m = median(vals)
            mag = abs(m)
            basis = f"{ev_type} 유형 과거 사례 {len(vals)}건 직후 {state['horizon_days']}영업일 변화 중앙값 ({fmt.signed(m, 2, FACTOR_BY_ID[fid].unit)})"
        else:
            mag = 0.25 * stats["hist_max"].get(fid, 1.0)
            basis = "과거 사례 통계 없음 · 과거 최대 변동폭의 25%로 가정"
        shocks.append(ShockItem(variable=fid, change=(1 if d == "+" else -1) * round(mag, 2 if FACTOR_BY_ID[fid].unit == "%p" else 1), basis=basis))
    return ScenarioShocks(shocks=shocks, horizon_days=state["horizon_days"])


def run(state: RunState, stats: dict) -> tuple[dict, dict]:
    horizon = state["horizon_days"]
    user_shocks = parse_natural(state["input_text"]) if state["entry"] == "scenario" else {}
    system = prompts.SCENARIO_BUILDER.replace("{factor_list}", factor_list_text(stats.get("unavailable")))
    ev_type = (state.get("event") or {}).get("type")
    analog_lines = []
    for t, items in stats["analogs"].items():
        for a in items:
            ch = ", ".join(f"{k} {v:+.2f}{FACTOR_BY_ID[k].unit}" for k, v in a["changes"].items() if k in FACTOR_BY_ID)
            analog_lines.append(f"- [{t}] {a['label']} ({a['date']}): {ch}")
    user = (f"horizon_days: {horizon}\n입구: {state['entry']}\n"
            + (f"자연어 시나리오: {state['input_text']}\n규칙 파서가 읽은 값: {json.dumps(user_shocks, ensure_ascii=False)}\n" if state["entry"] == "scenario" else "")
            + (f"파급 경로 그래프: {json.dumps(state.get('graph'), ensure_ascii=False)}\n" if state.get("graph") else "")
            + (f"이벤트 유형: {ev_type} — 크기를 정할 때 이 유형의 요약 중앙값을 쓴다\n" if ev_type else "")
            + "\n[유형별 과거 사례 요약 — 엔진이 계산한 중앙값·사분위·방향 일치율. 중앙값을 그대로 쓴다]\n"
            + analog_summary_text(stats, [ev_type] if ev_type else None)
            + "\n\n[과거 사례 직후 팩터 변화 (사례별)]\n" + "\n".join(analog_lines)
            + "\n\n[과거 최대 변동폭]\n" + ", ".join(f"{k} ±{v:.2f}{FACTOR_BY_ID[k].unit}" for k, v in stats["hist_max"].items() if k in FACTOR_BY_ID))
    res = llm.structured(system, user, ScenarioShocks, model=settings.model_default, effort="medium")
    if res.parsed is None:
        if res.error != "offline":
            raise llm.LLMError(res.error or "Scenario Builder 실패")
        if state["entry"] == "scenario":
            if not user_shocks:
                raise ValueError("시나리오에서 변수와 충격 크기를 읽지 못했습니다. 예: '유가 30% 급등 + 원화 10% 약세'")
            parsed = ScenarioShocks(shocks=[ShockItem(variable=k, change=v, basis="사용자 입력값") for k, v in user_shocks.items()], horizon_days=horizon)
        else:
            parsed = _offline_from_paths(state, stats)
    else:
        parsed = res.parsed
    # 사용자가 명시한 값은 LLM 출력보다 우선
    by_var = {s.variable: s for s in parsed.shocks if s.variable in FACTOR_BY_ID}
    for k, v in user_shocks.items():
        by_var[k] = ShockItem(variable=k, change=v, basis="사용자 입력값")
    shocks = []
    over = []
    dropped = [fid for fid in by_var if fid in (stats.get("unavailable") or [])]
    for fid in FACTOR_IDS:
        if fid not in by_var or fid in dropped:
            continue
        s = by_var[fid]
        hm = stats["hist_max"].get(fid)
        pct = abs(s.change) / hm * 100 if hm else None
        shocks.append({"variable": fid, "name": FACTOR_BY_ID[fid].name, "change": float(s.change), "unit": FACTOR_BY_ID[fid].unit,
                       "basis": s.basis, "hist_max": hm, "hist_pct": round(pct, 1) if pct is not None else None,
                       "over_hist": bool(pct is not None and pct > 100)})
        if pct is not None and pct > 100:
            over.append(fid)
    if not shocks:
        raise ValueError("충격 변수를 하나도 만들지 못했습니다")
    scenario = {"horizon_days": horizon, "shocks": shocks}
    meta = {"model": model_label(res.model), "tokens": (res.tokens_in, res.tokens_out),
            "summary": f"충격 변수 {len(shocks)}개 · 과거 최대 초과 {len(over)}",
            "note": " · ".join(x for x in [("과거 최대 변동폭 초과: " + ", ".join(over)) if over else "",
                                         ("시계열 미수집으로 제외: " + ", ".join(dropped)) if dropped else ""] if x)}
    return scenario, meta
