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
    if key == "amt":
        return fmt.amount(v)
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

    key_list = "\n".join(f"- {{{{{k}}}}}: {_render_value(k, outputs, scenario)}" for k in outputs)
    user = (f"[분석 대상]\n{json.dumps(ev or {'scenario_text': state['input_text']}, ensure_ascii=False)}\n"
            f"[포트폴리오] {state['title']} · 가상 모델 포트폴리오\n"
            f"[충격값]\n{json.dumps([{k: s[k] for k in ('variable', 'name', 'change', 'unit', 'basis')} for s in scenario['shocks']], ensure_ascii=False)}\n"
            f"[헤지 규칙 결과 — 문장에 쓸 때는 why_tpl/rule_tpl 의 자리표시자를 그대로 쓴다]\n{json.dumps(r['hedges'], ensure_ascii=False)}\n"
            f"[검증]\n{json.dumps(state.get('validation'), ensure_ascii=False)}\n"
            f"\n[수치 키 목록 — 반드시 이 키만 자리표시자로 사용]\n{key_list}")
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
    lines += ["", "## 4. 헤지 제안", ""]
    for h in r["hedges"]:
        lines.append(f"- **{h['title']}** — {h['why_tpl']} · 적용 규칙: {h['rule_tpl']} · `engine/hedge.py`")
    lines += ["", text.hedge_commentary, "", "## 5. 데이터 출처", ""]
    for c in citations:
        flag = " (합성 데이터)" if c["synthetic"] else ""
        lines.append(f"[{c['n']}] {c['name']}{flag} · 수집 {c['collected_at'] or '-'} · {c['license'] or '라이선스 미기재'}")
    lines += ["", f"계산 코드 해시 {calc['code_hash']} · engine v{calc['engine_version']}"]
    return "\n".join(lines), citations
