"""Agent 단위 테스트 (offline 규칙 경로) + Validator + Report Writer 치환."""
import pytest

from app.agents import validator
from app.agents.report_writer import substitute
from app.agents.scenario_builder import parse_natural


@pytest.mark.parametrize("text, expected", [
    ("유가 30% 급등 + 원화 10% 약세", {"WTI": 30.0, "USDKRW": 10.0}),
    ("미국 금리 1%p 인상", {"DGS10": 1.0}),
    ("반도체 업종 20% 하락", {"KOSPI_IT": -20.0}),
    ("원화 5% 강세", {"USDKRW": -5.0}),
    ("달러 3% 약세", {"USDKRW": -3.0}),
    ("코스피 8% 급락, 국고채 금리 50bp 상승", {"KOSPI": -8.0, "KTB3Y": 0.5}),
])
def test_parse_natural(text, expected):
    assert parse_natural(text) == expected


def test_parse_natural_ignores_unknown():
    assert parse_natural("날씨가 좋다") == {}


def test_substitute_marks_known_and_reports_unknown():
    md, unknown = substitute("손익 {{pnl}} · 범위 {{range.low}} · 없음 {{nope}}", {"pnl": -3.84, "range.low": -5.1}, {})
    assert "<!--k:pnl-->−3.8%<!--/k-->" in md
    assert "<!--k:range.low-->−5.1%<!--/k-->" in md
    assert "{{nope}}" in md and unknown == ["nope"]


def test_check_report_flags_uncited_numbers_only():
    ok = "## 1. 요약\n\n손익은 <!--k:pnl-->−3.8%<!--/k-->이다. 계산 ID `calc_12ab` · 기준일 2026-10-13\n\n[1] FRED · 수집 2026-10-13 · seed=42\n| 자산 | 14.0% |"
    assert validator.check_report(ok, {"pnl": -3.8}, 20) == []
    bad = "손실의 30% 이상이면 헤지한다."
    assert validator.check_report(bad, {}, 20) == ["출처 없는 수치 '30'"]
    assert validator.check_report("유가 30% 급등 시나리오", {}, 20, allowed=["유가 30% 급등"]) == []


def _state(**over):
    base = {
        "entry": "event", "horizon_days": 20,
        "graph": {"nodes": [{"id": "n1", "layer": "policy", "label": "a"},
                            {"id": "n2", "layer": "macro", "label": "b", "factor_id": "USDKRW"},
                            {"id": "n3", "layer": "asset", "label": "c"}]},
        "impact_paths": [{"steps": [{"from": "n1", "to": "n2", "direction": "+", "confidence": "high", "evidence": ["e1", "e2"]},
                                    {"from": "n2", "to": "n3", "direction": "-", "confidence": "mid", "evidence": ["e1"]}]}],
        "scenario": {"shocks": [{"variable": "USDKRW", "change": 5.0, "over_hist": False}]},
        "result": {"portfolio_pnl": -1.0, "by_asset": [{"ret": -2.0, "contribution": -1.0}], "range": {"low": -1.5, "high": -0.5}},
        "calc_log": {"inputs": {"shocks": {"USDKRW": 5.0}}},
        "event": {"missing_fields": []},
    }
    base.update(over)
    return base


def test_validator_passes_consistent_state():
    v = validator.check(_state(), synthetic=False)
    assert v["passed"] and v["status"] == "pass" and v["rules_passed"] == 4


def test_validator_rejects_high_without_evidence():
    st = _state()
    st["impact_paths"][0]["steps"][0]["evidence"] = ["e1"]
    v = validator.check(st, synthetic=False)
    assert not v["passed"]
    assert any(i["code"] == "high_without_evidence" and i["agent"] == "Impact Mapper" for i in v["issues"])


def test_validator_rejects_shock_outside_path():
    st = _state(scenario={"shocks": [{"variable": "USDKRW", "change": 5.0}, {"variable": "WTI", "change": 10.0}]})
    st["calc_log"]["inputs"]["shocks"]["WTI"] = 10.0
    v = validator.check(st, synthetic=False)
    assert any(i["code"] == "shock_not_in_path" and i["agent"] == "Scenario Builder" for i in v["issues"])


def test_validator_rejects_sum_mismatch():
    st = _state(result={"portfolio_pnl": -1.0, "by_asset": [{"ret": -2.0, "contribution": -0.7}], "range": {"low": -1.5, "high": -0.5}})
    v = validator.check(st, synthetic=False)
    assert any(i["code"] == "sum_mismatch" and i["agent"] == "Risk Engine" for i in v["issues"])


def test_validator_warns_but_passes_on_low_and_synthetic():
    st = _state()
    st["impact_paths"][0]["steps"][1].update({"confidence": "low", "evidence": []})
    v = validator.check(st, synthetic=True)
    assert v["passed"] and v["status"] == "warn"
    assert {i["code"] for i in v["issues"]} == {"low_evidence", "synthetic_data"}


def test_check_report_catches_korean_counters_and_allows_literals():
    assert validator.check_report("분석 기간은 20영업일이며 유사 구간 5개를 썼다.", {}, 20) != []
    assert validator.check_report("자산 KOSPI 200과 미국 주식 (S&P 500)", {}, 20, allowed=["KOSPI 200", "미국 주식 (S&P 500)"]) == []
    assert validator.check_report("손실 −1,240억 원", {}, 20) == ["출처 없는 수치 '−1,240'"]


def test_parse_natural_won_weakness_is_fx_up():
    assert parse_natural("원화 10% 하락") == {"USDKRW": 10.0}
    assert parse_natural("원화 10% 급락") == {"USDKRW": 10.0}
    assert parse_natural("원화 3% 절상") == {"USDKRW": -3.0}
