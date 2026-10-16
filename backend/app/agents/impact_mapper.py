"""Impact Mapper: event → impact_paths (최대 3개 경로, 경로당 4단계). 근거는 제공된 요약 통계에서만."""
from __future__ import annotations

import json
from datetime import date

from .. import llm, prompts
from ..config import settings
from ..engine.catalog import FACTOR_BY_ID
from ..models.state import Evidence, ImpactPaths, PathNode, PathStep, RunState
from .common import analog_summary_text, betas_text, factor_list_text, model_label

LAYER_NAME = {"policy": "정책", "industry": "산업", "macro": "거시 변수", "asset": "자산군"}


def _stats_text(stats: dict, event: dict, holdings_summary: list[dict]) -> str:
    """LLM에 주는 요약 통계. 시계열 원본 대신 사례별 누적 변화와 포트폴리오 구성만 넣는다."""
    lines = ["[과거 유사 사례 직후 20영업일 팩터 변화] (출처: engine/regimes.py · DB 시계열)"]
    for a in stats["analogs"].get(event["type"], []):
        ch = ", ".join(f"{k} {v:+.2f}{FACTOR_BY_ID[k].unit}" for k, v in a["changes"].items() if k in FACTOR_BY_ID)
        lines.append(f"- {a['label']} ({a['date']}): {ch}")
    if len(lines) == 1:
        lines.append("- (같은 유형의 과거 사례 통계 없음)")
    lines.append("\n[유형별 과거 사례 요약 — 팩터별 중앙값·사분위·방향 일치율] (출처: engine/regimes.py · DB 시계열)")
    lines.append(analog_summary_text(stats, [event["type"]]))
    lines.append("\n[자산별 팩터 민감도 — 일별 수익률 OLS 회귀] (출처: engine/factors.py · OLS 베타)")
    lines.append(betas_text(stats))
    if stats.get("unavailable"):
        lines.append(f"\n[이번 계산에서 제외된 팩터 — 시계열 미수집] {', '.join(stats['unavailable'])} (macro 노드로 쓰지 않는다)")
    lines.append("\n[팩터별 과거 20영업일 최대 변동폭] (출처: engine/regimes.py)")
    lines.append(", ".join(f"{k} ±{v:.2f}{FACTOR_BY_ID[k].unit}" for k, v in stats["hist_max"].items() if k in FACTOR_BY_ID))
    lines.append("\n[포트폴리오 구성] (출처: 가상 모델 포트폴리오)")
    for h in holdings_summary:
        lines.append(f"- {h['name']}: {h['asset_class']} · {h['currency']} · {h['sector']} · 비중 {h['weight']}%")
    return "\n".join(lines)


def _offline(event: dict, stats: dict, as_of: str) -> ImpactPaths:
    """규칙 기반 대체: 이벤트 유형별 표준 경로. 근거는 과거 사례 통계에서 만든다."""
    t = event["type"]
    analogs = stats["analogs"].get(t, [])
    ev: list[Evidence] = []
    for i, a in enumerate(analogs[:3]):
        parts = ", ".join(f"{k} {v:+.1f}{FACTOR_BY_ID[k].unit}" for k, v in a["changes"].items() if k in ("USDKRW", "KOSPI_IT", "KOSPI", "DGS10"))
        ev.append(Evidence(id=f"ev{i+1}", text=f"{a['label']} 직후 20영업일: {parts}", source="engine/regimes.py · DB 시계열"))
    ids = [e.id for e in ev]
    conf = "high" if len(ev) >= 2 else "mid" if ev else "low"
    # 포트폴리오 구성은 자산군 단계의 정량 근거가 된다
    comp = stats.get("_holdings") or []
    kr = sum(h["weight"] for h in comp if h["currency"] == "KRW" and h["asset_class"] == "주식")
    bond = sum(h["weight"] for h in comp if h["asset_class"] == "채권")
    ev.append(Evidence(id=f"ev{len(ev)+1}", text=f"국내 주식 비중 {kr:.0f}% · 채권 비중 {bond:.0f}%", source="가상 모델 포트폴리오"))
    pid = ev[-1].id
    asset_ids = ids[:1] + [pid]

    def c(evs: list[str]) -> str:
        """근거 수로 확신도를 정한다 (Validator 규칙과 동일: high ≥2, mid ≥1, 그 외 low)."""
        return "high" if len(evs) >= 2 else "mid" if evs else "low"
    label = event["title"][:18].rstrip(",· ")
    if t == "tariff":
        nodes = [PathNode(id="n1", label=label, layer="policy", factor_id=None, direction_text="출발 이벤트"),
                 PathNode(id="n2", label="대상 품목 수출 감소", layer="industry", factor_id=None, direction_text="관세 → 수출 (−)"),
                 PathNode(id="n3", label="원/달러 환율 상승", layer="macro", factor_id="USDKRW", direction_text="수출 감소 → 환율 (+)"),
                 PathNode(id="n4", label="KOSPI IT 업종 하락", layer="macro", factor_id="KOSPI_IT", direction_text="수출 감소 → IT 업종 (−)"),
                 PathNode(id="n5", label="미 국채 금리 하락", layer="macro", factor_id="DGS10", direction_text="위험회피 → 금리 (−)"),
                 PathNode(id="n6", label="국내 주식", layer="asset", factor_id=None, direction_text="IT 업종·환율 → 국내 주식 (−)"),
                 PathNode(id="n7", label="채권", layer="asset", factor_id=None, direction_text="금리 하락 → 채권 가격 (+)")]
        paths = [[PathStep(from_node="n1", to_node="n2", direction="-", confidence=c(ids), evidence_ids=ids),
                  PathStep(from_node="n2", to_node="n4", direction="+", confidence=c(ids), evidence_ids=ids),
                  PathStep(from_node="n4", to_node="n6", direction="+", confidence=c(asset_ids), evidence_ids=asset_ids)],
                 [PathStep(from_node="n2", to_node="n3", direction="-", confidence=c(ids[:1]), evidence_ids=ids[:1]),
                  PathStep(from_node="n3", to_node="n6", direction="-", confidence=c(asset_ids), evidence_ids=asset_ids)],
                 [PathStep(from_node="n1", to_node="n5", direction="-", confidence=c(ids[:1]), evidence_ids=ids[:1]),
                  PathStep(from_node="n5", to_node="n7", direction="-", confidence=c([pid]), evidence_ids=[pid])]]
    elif t == "rate":
        nodes = [PathNode(id="n1", label=label, layer="policy", factor_id=None, direction_text="출발 이벤트"),
                 PathNode(id="n2", label="달러 자금 조달비용 상승", layer="industry", factor_id=None, direction_text="금리 → 조달비용 (+)"),
                 PathNode(id="n3", label="미 국채 금리 상승", layer="macro", factor_id="DGS10", direction_text="정책금리 → 장기금리 (+)"),
                 PathNode(id="n4", label="원/달러 환율 상승", layer="macro", factor_id="USDKRW", direction_text="금리차 → 환율 (+)"),
                 PathNode(id="n5", label="국고채 금리 상승", layer="macro", factor_id="KTB3Y", direction_text="미 금리 → 국내 금리 (+)"),
                 PathNode(id="n6", label="채권", layer="asset", factor_id=None, direction_text="금리 상승 → 채권 가격 (−)"),
                 PathNode(id="n7", label="국내 주식", layer="asset", factor_id=None, direction_text="환율·금리 → 국내 주식 (−)")]
        paths = [[PathStep(from_node="n1", to_node="n3", direction="+", confidence=c(ids), evidence_ids=ids),
                  PathStep(from_node="n3", to_node="n6", direction="-", confidence=c(asset_ids), evidence_ids=asset_ids)],
                 [PathStep(from_node="n1", to_node="n2", direction="+", confidence=c(ids[:1]), evidence_ids=ids[:1]),
                  PathStep(from_node="n2", to_node="n4", direction="+", confidence=c(ids), evidence_ids=ids),
                  PathStep(from_node="n4", to_node="n7", direction="-", confidence=c(asset_ids), evidence_ids=asset_ids)],
                 [PathStep(from_node="n3", to_node="n5", direction="+", confidence=c(ids[:1]), evidence_ids=ids[:1]),
                  PathStep(from_node="n5", to_node="n6", direction="-", confidence=c([pid]), evidence_ids=[pid])]]
    else:
        nodes = [PathNode(id="n1", label=label, layer="policy", factor_id=None, direction_text="출발 이벤트"),
                 PathNode(id="n2", label="대상 산업 공급 차질", layer="industry", factor_id=None, direction_text="규제 → 공급 (−)"),
                 PathNode(id="n3", label="KOSPI IT 업종 하락", layer="macro", factor_id="KOSPI_IT", direction_text="공급 차질 → IT 업종 (−)"),
                 PathNode(id="n4", label="KOSPI 하락", layer="macro", factor_id="KOSPI", direction_text="업종 → 시장 전체 (−)"),
                 PathNode(id="n5", label="원/달러 환율 상승", layer="macro", factor_id="USDKRW", direction_text="외국인 매도 → 환율 (+)"),
                 PathNode(id="n6", label="국내 주식", layer="asset", factor_id=None, direction_text="업종·시장 → 국내 주식 (−)")]
        paths = [[PathStep(from_node="n1", to_node="n2", direction="+", confidence=c(ids), evidence_ids=ids),
                  PathStep(from_node="n2", to_node="n3", direction="-", confidence=c(ids), evidence_ids=ids),
                  PathStep(from_node="n3", to_node="n6", direction="+", confidence=c(asset_ids), evidence_ids=asset_ids)],
                 [PathStep(from_node="n3", to_node="n4", direction="+", confidence=c(ids[:1]), evidence_ids=ids[:1]),
                  PathStep(from_node="n4", to_node="n6", direction="+", confidence=c(asset_ids), evidence_ids=asset_ids)],
                 [PathStep(from_node="n4", to_node="n5", direction="-", confidence=c(ids[:1]), evidence_ids=ids[:1])]]
    return ImpactPaths(nodes=nodes, paths=paths, evidence=ev)


def to_graph(ip: ImpactPaths, as_of: str) -> tuple[list[dict], dict]:
    """ImpactPaths → RunState.impact_paths + 화면용 graph."""
    ev_by_id = {e.id: e for e in ip.evidence}
    node_conf: dict[str, str] = {}
    node_evidence: dict[str, list[str]] = {n.id: [] for n in ip.nodes}
    edges = []
    for path in ip.paths:
        for s in path:
            edges.append({"source": s.from_node, "target": s.to_node, "direction": s.direction, "confidence": s.confidence})
            rank = {"high": 3, "mid": 2, "low": 1}
            if rank[s.confidence] > rank.get(node_conf.get(s.to_node, "low"), 0) or s.to_node not in node_conf:
                node_conf[s.to_node] = s.confidence
            for eid in s.evidence_ids:
                if eid in ev_by_id and eid not in node_evidence.setdefault(s.to_node, []):
                    node_evidence[s.to_node].append(eid)
    nodes = []
    for n in ip.nodes:
        nodes.append({
            "id": n.id, "label": n.label, "layer": n.layer, "layer_name": LAYER_NAME[n.layer],
            "confidence": "high" if n.layer == "policy" else node_conf.get(n.id, "low"), "factor_id": n.factor_id,
            "direction_text": n.direction_text,
            "evidence": [{"id": e, "text": ev_by_id[e].text, "source": ev_by_id[e].source, "collected_at": as_of}
                         for e in node_evidence.get(n.id, [])],
        })
    impact_paths = [{"path_id": f"p{i+1}", "excluded": False, "reason": None,
                     "steps": [{"from": s.from_node, "to": s.to_node, "direction": s.direction,
                                "confidence": s.confidence, "evidence": s.evidence_ids} for s in path]}
                    for i, path in enumerate(ip.paths)]
    return impact_paths, {"nodes": nodes, "edges": edges}


def run(state: RunState, stats: dict, holdings_summary: list[dict], rejected_issues: list[str] | None) -> tuple[list[dict], dict, dict]:
    event = state["event"]
    as_of = state.get("as_of") or date.today().isoformat()
    system = prompts.IMPACT_MAPPER.replace("{factor_list}", factor_list_text(stats.get("unavailable")))
    user = f"[정책 이벤트]\n{json.dumps(event, ensure_ascii=False)}\n\n{_stats_text(stats, event, holdings_summary)}"
    if rejected_issues:
        user += "\n\n" + prompts.IMPACT_MAPPER_RETRY.format(issues="\n".join(f"- {i}" for i in rejected_issues))
    res = llm.structured(system, user, ImpactPaths, model=settings.model_impact_mapper, effort="medium", max_tokens=16000)
    if res.parsed is None:
        if res.error != "offline":
            raise llm.LLMError(res.error or "Impact Mapper 실패")
        ip = _offline(event, {**stats, "_holdings": holdings_summary}, as_of)
    else:
        ip = _normalize(res.parsed)
    impact_paths, graph = to_graph(ip, as_of)
    n_steps = sum(len(p["steps"]) for p in impact_paths)
    n_low = sum(1 for p in impact_paths for s in p["steps"] if s["confidence"] == "low")
    meta = {"model": model_label(res.model), "tokens": (res.tokens_in, res.tokens_out),
            "summary": f"경로 {len(impact_paths)}개 · 단계 {n_steps}개 (low {n_low}) · 근거 {len(ip.evidence)}건"}
    return impact_paths, graph, meta


def _normalize(ip: ImpactPaths) -> ImpactPaths:
    """LLM 출력의 형식적 제약을 강제한다 (경로 3개, 4단계, 유효 노드·팩터)."""
    node_ids = {n.id for n in ip.nodes}
    for n in ip.nodes:
        if n.factor_id and n.factor_id not in FACTOR_BY_ID:
            n.factor_id = None
    ev_ids = {e.id for e in ip.evidence}
    paths = []
    for p in ip.paths[:3]:
        steps = [s for s in p[:4] if s.from_node in node_ids and s.to_node in node_ids]
        for s in steps:
            s.evidence_ids = [e for e in s.evidence_ids if e in ev_ids]
            if not s.evidence_ids and s.confidence != "low":
                s.confidence = "low"
        if steps:
            paths.append(steps)
    ip.paths = paths
    return ip
