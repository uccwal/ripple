"""Report Writer: 보고서 Markdown. 수치는 calc_log.outputs 키를 자리표시자로만 쓰고 엔진이 치환한다."""
from __future__ import annotations

import json
import re

from .. import llm, prompts
from ..config import settings
from ..engine import fmt
from ..engine.catalog import FACTOR_BY_ID
from ..models.state import ReportText, RunState
from .common import model_label

PLACEHOLDER = re.compile(r"\{\{([\w.:\-]+)\}\}")


def _render_value(key: str, outputs: dict, scenario: dict) -> str:
    v = outputs[key]
    if key in ("pnl", "range.low", "range.high") or key.startswith("reg.") and key != "reg.n" or key.endswith(".ret") or key.endswith(".pnl"):
        return fmt.signed(v)
    if key == "amt" or key.endswith(".amt"):
        return fmt.amount(v)
    if key == "act.days":
        return f"{int(v)}영업일"
    if key == "act.hit_rate":
        return f"{int(v)}%"
    if key == "act.err":
        return f"{v:.1f}%p"
    if key.startswith("act.f:"):
        fid = key[6:]
        unit = FACTOR_BY_ID[fid].unit if fid in FACTOR_BY_ID else "%"
        return fmt.signed(v, fmt.shock_digits(unit), unit)
    if key == "aum":
        return f"{v:,.0f}억 원"
    if key == "reg.n":
        return f"{int(v)}개"
    if key == "horizon":
        return f"{int(v)}영업일"
    if key in ("event.value_text", "event.date"):
        return str(v)
    if key.startswith("fc:") and key.endswith(".share") or key.startswith("hedge.") or key.startswith("rule."):
        return f"{int(v)}%"
    if key.startswith("fc:"):
        return fmt.signed(v, 2, "%p")
    if key.startswith("f:"):
        fid = key[2:]
        unit = FACTOR_BY_ID[fid].unit
        return fmt.signed(v, fmt.shock_digits(unit), unit)
    if key.endswith(".contribution"):
        return fmt.signed(v, 2, "%p")
    if key.endswith(".weight"):
        return f"{v:.1f}%"
    if key.endswith(".similarity"):
        return f"{v:.2f}"
    return str(v)


def describe_key(key: str, names: dict[str, str]) -> str:
    """수치 키의 의미 한 줄 (LLM 이 키를 잘못된 뜻으로 쓰지 않도록)."""
    fixed = {
        "pnl": "포트폴리오 예상 손익 (팩터 모델, %)", "amt": "예상 손익 금액 (억 원)",
        "range.low": "추정 범위 하한 (95%)", "range.high": "추정 범위 상한 (95%)", "aum": "운용자산",
        "reg.n": "과거 유사 국면 '구간' 수 — 사건·사례 수가 아님", "reg.median": "유사 국면 구간들의 실제 손익 중앙값",
        "reg.low": "유사 국면 실제 손익 최소", "reg.high": "유사 국면 실제 손익 최대",
        "horizon": "분석 기간 (영업일)", "event.value_text": "이벤트 원문의 핵심 수치", "event.date": "이벤트 발표일",
        "rule.fx": "헤지 규칙 기준값 — 환율 기여 비중", "rule.sector": "헤지 규칙 기준값 — 업종 기여 비중",
        "rule.rate": "헤지 규칙 기준값 — 금리 기여 비중",
        "act.pnl": "사후 검증 — 발표 후 실제 포트폴리오 손익 (실제 시장 데이터)", "act.days": "사후 검증 관측 기간 (영업일)",
        "act.err": "추정 손익과 실제 손익의 차이 (절댓값)", "act.hit_rate": "충격 변수 방향 적중률 (실제 변화와 부호 일치 비율)",
    }
    if key in fixed:
        return fixed[key]
    if key.startswith("h:"):
        aid, _, attr = key[2:].partition(".")
        nm = names.get(aid, aid)
        return {"ret": f"{nm} 예상 수익률", "contribution": f"{nm}의 포트폴리오 손익 기여 (%p)", "weight": f"{nm} 비중"}.get(attr, key)
    if key.startswith("fc:"):
        fid, _, attr = key[3:].partition(".")
        nm = FACTOR_BY_ID[fid].name if fid in FACTOR_BY_ID else fid
        return f"{nm} 팩터가 손실에서 차지하는 비중" if attr == "share" else f"{nm} 팩터의 손익 기여 (%p)"
    if key.startswith("f:"):
        fid = key[2:]
        return f"{FACTOR_BY_ID[fid].name if fid in FACTOR_BY_ID else fid} 충격값 (시나리오)"
    if key.startswith("hedge."):
        return "헤지 규칙이 측정한 기여 비중"
    if key.startswith("act.f:"):
        fid = key[6:]
        return f"{FACTOR_BY_ID[fid].name if fid in FACTOR_BY_ID else fid} 발표 후 실제 변화"
    if key.startswith("xp:"):
        pid, _, attr = key[3:].partition(".")
        return f"포트폴리오 {pid}에 같은 시나리오를 적용한 " + ("예상 손익 금액" if attr == "amt" else "예상 손익")
    if key.startswith("regime."):
        return "개별 유사 국면 구간의 유사도/실제 손익"
    return ""


def substitute(text: str, outputs: dict, scenario: dict) -> tuple[str, list[str]]:
    """{{키}} → 서식 적용 값(마커 포함). 알 수 없는 키는 그대로 두고 위반으로 보고."""
    unknown: list[str] = []

    def rep(m: re.Match) -> str:
        k = m.group(1)
        if k not in outputs:
            unknown.append(k)
            return m.group(0)
        return f"<!--k:{k}-->{_render_value(k, outputs, scenario)}<!--/k-->"

    return PLACEHOLDER.sub(rep, text), unknown


def _offline_text(state: RunState) -> ReportText:
    r = state["result"]
    ev = state.get("event")
    subject = f"정책 이벤트 '{ev['title']}'" if ev else f"직접 입력 시나리오 '{state['input_text']}'"
    reg = " 과거 유사 국면 {{reg.n}} 구간의 실제 손익 중앙값은 {{reg.median}}로, 팩터 모델 추정과 함께 참고한다." if r.get("regime_estimate") else ""
    summary = (f"{subject}가 가상 모델 포트폴리오에 미치는 {{{{horizon}}}} 영향을 팩터 모델로 추정한 결과 "
               f"예상 손익은 {{{{pnl}}}}({{{{amt}}}})이며, 베타 추정오차를 반영한 범위는 {{{{range.low}}}} ~ {{{{range.high}}}}이다.{reg}")
    top = r["top_contributors"][0] if r["top_contributors"] else None
    top_name = next((a["name"] for a in r["by_asset"] if a["asset_id"] == top), "")
    path_c = (f"손실 기여가 가장 큰 자산은 {top_name}({{{{h:{top}.contribution}}}})이다. " if top else "") + \
             ("정책 → 산업 → 거시 변수 → 자산군 경로 중 근거가 불충분한 단계는 그래프에 점선으로 표시했다." if ev else
              "직접 입력한 충격값을 그대로 적용했으며 파급 경로 추론은 생략했다.")
    if r["hedges"]:
        hedge_c = " ".join(f"{h['title']}: {h['why_tpl']} (규칙: {h['rule_tpl']})." for h in r["hedges"])
    else:
        hedge_c = "헤지 규칙의 기준값을 넘는 단일 팩터·업종 기여가 없어 별도 헤지 제안은 없다."
    return ReportText(summary=summary, path_commentary=path_c, hedge_commentary=hedge_c)


def extra_outputs(state: RunState) -> dict:
    """계산 로그 외에 보고서가 인용할 수 있는 키: 분석 기간, 이벤트 핵심 수치·발표일."""
    out = {"horizon": state["horizon_days"]}
    ev = state.get("event") or {}
    if ev.get("value_text"):
        out["event.value_text"] = ev["value_text"]
    if ev.get("announced_at"):
        out["event.date"] = ev["announced_at"]
    return out


def run(state: RunState, rejected: list[str] | None = None) -> tuple[dict, dict]:
    r = state["result"]
    calc = state["calc_log"]
    outputs = dict(calc["outputs"])
    outputs.update(extra_outputs(state))
    scenario = state["scenario"]
    ev = state.get("event")

    names = {a["asset_id"]: a["name"] for a in r["by_asset"]}
    key_list = "\n".join(f"- {{{{{k}}}}}: {_render_value(k, outputs, scenario)} — {describe_key(k, names)}" for k in outputs)
    unavailable = (calc.get("inputs") or {}).get("factors_unavailable") or []
    user = (f"[분석 대상]\n{json.dumps(ev or {'scenario_text': state['input_text']}, ensure_ascii=False)}\n"
            f"[포트폴리오] {state['title']} · 가상 모델 포트폴리오\n"
            f"[충격값]\n{json.dumps([{k: s[k] for k in ('variable', 'name', 'change', 'unit', 'basis')} for s in scenario['shocks']], ensure_ascii=False)}\n"
            f"[헤지 규칙 결과 — 문장에 쓸 때는 why_tpl/rule_tpl 의 자리표시자를 그대로 쓴다]\n{json.dumps(r['hedges'], ensure_ascii=False)}\n"
            f"[검증]\n{json.dumps(state.get('validation'), ensure_ascii=False)}\n"
            + (f"[데이터 한계] 시계열 미수집으로 제외된 팩터: {', '.join(unavailable)} — 요약의 유의점에 한 줄 언급\n" if unavailable else "")
            + f"\n[수치 키 목록 — 반드시 이 키만 자리표시자로 사용]\n{key_list}")
    if rejected:
        user += ("\n\n[반려] 이전 초안은 Validator가 반려했다. 아래 수치가 자리표시자 없이 쓰였다. "
                 "숫자(연도·개수·퍼센트 포함)는 전부 {{키}} 로만 쓰고, 키가 없는 숫자는 문장에서 빼라.\n- " + "\n- ".join(rejected))
    res = llm.structured(prompts.REPORT_WRITER, user, ReportText, model=settings.model_default, effort="low")
    if res.parsed is None:
        if res.error != "offline":
            raise llm.LLMError(res.error or "Report Writer 실패")
        text = _offline_text(state)
    else:
        text = res.parsed

    md, citations = _assemble(state, text, outputs)
    unknown_total: list[str] = []
    md, unknown = substitute(md, outputs, scenario)
    unknown_total += unknown
    meta = {"model": model_label(res.model), "tokens": (res.tokens_in, res.tokens_out),
            "summary": f"5개 섹션 · 인용 {len(citations)}건", "unknown_keys": unknown_total}
    return {"markdown": md, "citations": citations}, meta


def _assemble(state: RunState, text: ReportText, outputs: dict) -> tuple[str, list[dict]]:
    r = state["result"]
    calc = state["calc_log"]
    ev = state.get("event")
    scenario = state["scenario"]
    sources = calc["inputs"]["sources"]
    citations = [{"n": i + 1, "name": s["name"], "collected_at": s["collected_at"], "url": s["url"],
                  "license": s["license"], "synthetic": s["synthetic"]} for i, s in enumerate(sources)]
    cite_idx = {s["series_id"]: i + 1 for i, s in enumerate(sources)}

    title = ev["title"] if ev else state["input_text"]
    lines = [f"# {title}", "",
             f"가상 모델 포트폴리오 · 분석 기간 {{{{horizon}}}} · 기준일 {calc['inputs']['as_of']} · 계산 ID `{calc['calc_id']}`", "",
             "## 1. 요약", "", text.summary, ""]
    lines += ["## 2. 파급 경로", ""]
    if ev and state.get("impact_paths"):
        names = {n["id"]: n["label"] for n in state["graph"]["nodes"]}
        conf_txt = {"high": "확신도 높음", "mid": "확신도 중간", "low": "근거 불충분"}
        for i, p in enumerate(state["impact_paths"]):
            chain = " → ".join([names[p["steps"][0]["from"]]] + [names[s["to"]] for s in p["steps"]])
            worst = min((s["confidence"] for s in p["steps"]), key=lambda c: {"high": 3, "mid": 2, "low": 1}[c])
            lines.append(f"{i + 1}. {chain} — {conf_txt[worst]}")
        lines.append("")
    lines += [text.path_commentary, ""]
    lines += ["### 적용 충격값", "", "| 변수 | 충격값 | 근거 |", "| --- | --- | --- |"]
    for s in scenario["shocks"]:
        lines.append(f"| {s['name']} | {{{{f:{s['variable']}}}}} | {s['basis']} |")
    lines += ["", "## 3. 손익", "",
              f"포트폴리오 예상 손익 {{{{pnl}}}} ({{{{amt}}}}), 추정 범위 {{{{range.low}}}} ~ {{{{range.high}}}}."]
    if r.get("regime_estimate"):
        lines.append(f"과거 유사 국면 {{{{reg.n}}}} 구간 실제 손익 중앙값 {{{{reg.median}}}} (범위 {{{{reg.low}}}} ~ {{{{reg.high}}}}).")
    lines += ["", "| 자산 | 비중 | 손익 | 기여도 |", "| --- | --- | --- | --- |"]
    for aid in r["top_contributors"]:
        a = next(x for x in r["by_asset"] if x["asset_id"] == aid)
        lines.append(f"| {a['name']} | {{{{h:{aid}.weight}}}} | {{{{h:{aid}.ret}}}} | {{{{h:{aid}.contribution}}}} |")
    others = [x for x in (r.get("cross_portfolio") or []) if not x.get("current") and x.get("pnl") is not None]
    if others:
        lines += ["", "### 다른 모델 포트폴리오에 같은 시나리오 적용", "", "| 포트폴리오 | 예상 손익 | 금액 | 최대 손실 기여 자산 |", "| --- | --- | --- | --- |"]
        for x in others:
            lines.append(f"| {x['name']} | {{{{xp:{x['portfolio_id']}.pnl}}}} | {{{{xp:{x['portfolio_id']}.amt}}}} | {x['worst_asset'] or '-'} |")
    lines += ["", "## 4. 헤지 제안", ""]
    for h in r["hedges"]:
        lines.append(f"- **{h['title']}** — {h['why_tpl']} · 적용 규칙: {h['rule_tpl']} · `engine/hedge.py`")
    lines += ["", text.hedge_commentary, ""]
    sec = 5
    act = r.get("actual")
    if act:
        lines += [f"## {sec}. 사후 검증 — 발표 후 실제 시장 움직임", ""]
        sec += 1
        tail = "" if act["complete"] else " 관측 기간이 분석 기간에 못 미쳐 잠정치다."
        if act.get("portfolio_pnl") is not None:
            lines.append("발표 전 마지막 거래일 종가를 기준으로 {{act.days}} 뒤 실제 포트폴리오 손익은 {{act.pnl}}이며, "
                         "팩터 모델 추정 {{pnl}}과의 차이는 {{act.err}}이다." + tail)
        else:
            lines.append("자산 가격 데이터가 발표 시점을 덮지 못해 포트폴리오 실제 손익은 계산하지 않았다. 팩터 변화만 비교한다." + tail)
        if "factor_hit_rate" in act and act["factor_hit_rate"] is not None:
            lines.append("시나리오 충격 변수의 방향 적중률은 {{act.hit_rate}}이다.")
        lines += ["", "| 변수 | 시나리오 충격 | 실제 변화 | 방향 |", "| --- | --- | --- | --- |"]
        for k, f in act["factors"].items():
            shock = f"{{{{f:{k}}}}}" if f.get("shock") is not None else "-"
            mark = "적중" if f.get("hit") else ("불일치" if f.get("hit") is False else "-")
            lines.append(f"| {f['name']} | {shock} | {{{{act.f:{k}}}}} | {mark} |")
        lines += [""]
    lines += [f"## {sec}. 데이터 출처", ""]
    for c in citations:
        flag = " (합성 데이터)" if c["synthetic"] else ""
        lines.append(f"[{c['n']}] {c['name']}{flag} · 수집 {c['collected_at'] or '-'} · {c['license'] or '라이선스 미기재'}")
    lines += ["", f"계산 코드 해시 {calc['code_hash']} · engine v{calc['engine_version']}"]
    return "\n".join(lines), citations
