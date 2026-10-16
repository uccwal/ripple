"""Risk Engine 단위 테스트: 회귀, 충격 적용, 범위, 유사 국면, 헤지 규칙, 서식."""
import math

import numpy as np
import pandas as pd
import pytest

from app.engine import fmt, risk
from app.engine.factors import ols
from app.engine.hedge import suggest
from app.engine.regimes import similarity_scores, top_regimes


def test_ols_recovers_known_betas():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(2000, 2))
    y = 0.5 + 1.5 * X[:, 0] - 2.0 * X[:, 1] + rng.normal(scale=0.1, size=2000)
    coef, se, r2 = ols(y, X)
    assert coef[0] == pytest.approx(0.5, abs=0.02)
    assert coef[1] == pytest.approx(1.5, abs=0.02)
    assert coef[2] == pytest.approx(-2.0, abs=0.02)
    assert r2 > 0.99
    assert all(s > 0 for s in se)


def test_prepare_fits_all_holdings(session):
    ctx = risk.prepare(session, "pf_a", None, 20)
    assert len(ctx.fits) == len(ctx.holdings) == 8
    for h in ctx.holdings:
        assert set(ctx.fits[h.asset_id].betas) == set(h.factors)
    # 듀레이션 채권: 금리 베타 ≈ −duration
    assert ctx.fits["UST10"].betas["DGS10"] == pytest.approx(-8.7, abs=0.2)
    assert ctx.synthetic is True


def test_as_of_filter_excludes_future(session):
    ctx = risk.prepare(session, "pf_a", pd.Timestamp("2019-07-01").date(), 20)
    assert ctx.levels.index.max() <= pd.Timestamp("2019-07-01")
    assert ctx.as_of.isoformat() == "2019-07-01"


def test_compute_identities(session):
    ctx = risk.prepare(session, "pf_a", None, 20)
    shocks = {"USDKRW": 5.0, "KOSPI_IT": -12.0, "DGS10": -0.15}
    regs = risk.find_regimes(ctx, shocks)
    out = risk.compute(ctx, shocks, regs, "run_test")
    r = out["result"]
    # ΔP = Σ wᵢ ΔRᵢ
    assert sum(a["contribution"] for a in r["by_asset"]) == pytest.approx(r["portfolio_pnl"])
    # 팩터 기여 합 = ΔP
    assert sum(f["contribution"] for f in r["factor_contrib"]) == pytest.approx(r["portfolio_pnl"])
    assert r["range"]["low"] <= r["portfolio_pnl"] <= r["range"]["high"]
    assert r["pnl_amount"] == pytest.approx(r["portfolio_pnl"] / 100 * ctx.portfolio.aum, abs=5)  # 10억 원 단위 반올림
    assert len(r["top_contributors"]) == 5
    # 계산 로그: 모든 보고서 키 존재, 코드 해시 형식
    log = out["calc_log"]
    assert log["code_hash"].startswith("sha256:")
    for k in ("pnl", "amt", "range.low", "range.high", "rule.fx"):
        assert k in log["outputs"]
    assert set(log["entries"]) >= {"pnl", "amt", "range", "model"} | {f"h:{a['asset_id']}" for a in r["by_asset"]}
    assert all(s["synthetic"] for s in log["inputs"]["sources"])


def test_zero_shock_gives_zero_pnl(session):
    ctx = risk.prepare(session, "pf_b", None, 20)
    out = risk.compute(ctx, {"USDKRW": 0.0}, [], "run_zero")
    assert out["result"]["portfolio_pnl"] == 0.0
    assert out["result"]["hedges"] == []


def test_regimes_are_non_overlapping_and_sorted(session):
    ctx = risk.prepare(session, "pf_a", None, 20)
    regs = top_regimes(ctx.window_changes, {"USDKRW": 5.0, "KOSPI_IT": -12.0}, 20)
    assert 1 <= len(regs) <= 5
    sims = [r.similarity for r in regs]
    assert sims == sorted(sims, reverse=True)
    for a in regs:
        for b in regs:
            if a is not b:
                assert a.end <= b.start or b.end <= a.start


def test_similarity_direction_matters():
    idx = pd.date_range("2020-01-01", periods=3)
    windows = pd.DataFrame({"A": [1.0, -1.0, 1.0], "B": [-1.0, 1.0, 1.0]}, index=idx)
    s = similarity_scores(windows, {"A": 1.0, "B": -1.0})
    assert s.iloc[0] > s.iloc[2] > s.iloc[1]


def test_hedge_rules():
    hedges = suggest(-4.0, {"USDKRW": -1.6, "KOSPI_IT": -2.0, "DGS10": -0.4}, {"반도체": -2.0, "국채": -0.4}, {"반도체": "KR_SEMI"})
    ids = [h.rule_id for h in hedges]
    assert "fx" in ids and "sector" in ids and "rate" not in ids
    assert suggest(2.0, {"USDKRW": 1.0}, {}, {}) == []
    assert "{{rule.fx}}" in hedges[0].rule_tpl


def test_fmt_unicode_minus_and_signs():
    assert fmt.signed(-3.84) == "−3.8%"
    assert fmt.signed(2.0) == "+2.0%"
    assert fmt.signed(0.0) == "0.0%"
    assert fmt.signed(-0.154, 2, "%p") == "−0.15%p"
    assert fmt.amount(-1237) == "−1,240억 원"
    assert fmt.signed(float("nan")) == "—"
    assert "−" in fmt.plain(-1.5)


def test_top_contributors_by_absolute_value(session):
    ctx = risk.prepare(session, "pf_a", None, 20)
    out = risk.compute(ctx, {"USDKRW": -10.0}, [], "run_gain")  # 원화 강세 → 원화 자산 이익
    r = out["result"]
    tops = [abs(a["contribution"]) for a in r["by_asset"] if a["asset_id"] in r["top_contributors"]]
    others = [abs(a["contribution"]) for a in r["by_asset"] if a["asset_id"] not in r["top_contributors"]]
    assert min(tops) >= max(others)


def test_prepare_excludes_missing_factor_series(session):
    """팩터 시계열이 없으면 계산을 멈추지 않고 그 팩터만 제외하며 calc_log 에 기록한다."""
    from sqlalchemy import delete

    from app.engine import risk
    from app.models.tables import SeriesValue

    session.execute(delete(SeriesValue).where(SeriesValue.series_id == "DXY_BROAD"))
    try:
        ctx = risk.prepare(session, "pf_a", None, 20)
        assert ctx.unavailable_factors == ["DXY_BROAD"]
        assert "DXY_BROAD" not in ctx.factor_ret.columns and "DXY_BROAD" not in ctx.window_changes.columns
        assert "DXY_BROAD" not in ctx.fits["US_EQ"].betas and "WTI" in ctx.fits["OIL"].betas
        stats = risk.scenario_stats(ctx)
        assert "DXY_BROAD" in stats["unavailable"] and "DXY_BROAD" not in stats["available"]
        out = risk.compute(ctx, {"WTI": 10.0, "DXY_BROAD": 3.0}, [], "run_x")
        assert out["calc_log"]["inputs"]["factors_unavailable"] == ["DXY_BROAD"]
        assert "f:DXY_BROAD" not in out["calc_log"]["outputs"]
        assert not ctx.window_changes.dropna().empty  # 유사 국면 탐색이 가능해야 한다
    finally:
        session.rollback()


def test_analog_summary_and_betas_in_stats(session):
    from app.engine import risk
    from app.engine.regimes import analog_summary

    summ = analog_summary([{"changes": {"USDKRW": 2.0, "KOSPI": -3.0}}, {"changes": {"USDKRW": 4.0, "KOSPI": 1.0}},
                           {"changes": {"USDKRW": -1.0}}])
    assert summ["USDKRW"] == {"n": 3, "median": 2.0, "p25": 0.5, "p75": 3.0, "up_share": pytest.approx(2 / 3)}
    assert summ["KOSPI"]["n"] == 2 and summ["KOSPI"]["up_share"] == 0.5
    ctx = risk.prepare(session, "pf_a", None, 20)
    stats = risk.scenario_stats(ctx)
    assert set(stats["analog_summary"]) == {"tariff", "rate", "regulation", "fx", "macro"}
    assert stats["analog_summary"]["tariff"]["USDKRW"]["n"] >= 3
    b = stats["betas"]["KR_SEMI"]
    assert set(b["factors"]) == {"KOSPI_IT", "USDKRW"} and b["factors"]["KOSPI_IT"]["t"] is not None
    assert stats["available"] == [f for f in risk.FACTOR_IDS if f not in stats["unavailable"]]


def test_actual_outcome_and_cross_portfolio(session):
    from datetime import date

    from app.engine import outcome, risk
    from app.models.tables import Holding

    holdings = list(session.scalars(__import__("sqlalchemy").select(Holding).where(Holding.portfolio_id == "pf_a")))
    shocks = {"USDKRW": 3.0, "KOSPI_IT": -8.0, "DGS10": -0.2}
    act = outcome.actual_outcome(session, holdings, date(2022, 6, 16), 20, shocks, estimate_pnl=-3.0)
    assert act is not None and act["complete"] is True and act["days"] == 20
    assert act["start"] < "2022-06-16" <= act["end"]
    assert set(shocks) <= set(act["factors"]) and act["factors"]["USDKRW"]["hit"] in (True, False)
    assert act["factors"]["WTI"]["hit"] is None  # 충격이 없는 변수는 판정하지 않는다
    assert act["portfolio_pnl"] is not None and act["abs_error"] is not None and act["direction_hit"] in (True, False)
    assert 0 <= act["factor_hit_rate"] <= 1 and act["factors_judged"] == 3
    # 발표일이 데이터 마지막 날이면 None, 아직 horizon 이 안 지났으면 잠정
    assert outcome.actual_outcome(session, holdings, date(2099, 1, 1), 20, shocks, None) is None

    ctx = risk.prepare(session, "pf_a", None, 20)
    out = risk.compute(ctx, shocks, [], "run_t")
    cross = outcome.cross_portfolio(session, "pf_a", ctx.as_of, 20, shocks, "run_t")
    assert [c["portfolio_id"] for c in cross] == ["pf_b"] and cross[0]["pnl"] is not None and cross[0]["error"] is None
    risk.attach_extras(out, ctx, act, cross)
    r, o = out["result"], out["calc_log"]["outputs"]
    assert r["cross_portfolio"][0]["current"] is True and r["cross_portfolio"][1]["portfolio_id"] == "pf_b"
    assert "xp:pf_b.pnl" in o and "xp:pf_b.amt" in o and "act.pnl" in o and "act.hit_rate" in o and "act.f:USDKRW" in o
    assert "xp" in out["calc_log"]["entries"] and "act" in out["calc_log"]["entries"]


def test_regime_summary_describes_top_factor_moves(session):
    import pandas as pd

    from app.engine import risk
    from app.engine.regimes import describe_changes

    row = pd.Series({"USDKRW": 4.9, "KOSPI": -10.5, "DGS10": 0.05})
    std = pd.Series({"USDKRW": 2.0, "KOSPI": 5.0, "DGS10": 0.3})
    txt = describe_changes(row, std)
    assert "원/달러 환율 +4.9%" in txt and "KOSPI −10.5%" in txt and "국채" not in txt
    ctx = risk.prepare(session, "pf_a", None, 20)
    regs = risk.find_regimes(ctx, {"USDKRW": 3.0, "KOSPI_IT": -8.0})
    assert regs and all(r.summary for r in regs)


def test_outputs_have_shock_key_for_every_factor_and_worst_is_a_loser(session):
    from app.engine import risk
    from app.engine.outcome import summarize_cases

    ctx = risk.prepare(session, "pf_b", None, 20)
    out = risk.compute(ctx, {"KOSPI_IT": -8.0, "DGS2": 0.3, "USDKRW": -10.0}, [], "run_t")
    o = out["calc_log"]["outputs"]
    assert "f:KOSPI_IT" in o and "f:DGS2" in o  # pf_b 에는 KOSPI_IT·DGS2 노출 자산이 없어도 충격값 키는 있어야 한다
    risk.attach_extras(out, ctx, None, [])
    main = out["result"]["cross_portfolio"][0]
    assert main["worst_contribution"] is None or main["worst_contribution"] < 0
    s = summarize_cases([{"direction_hit": True, "abs_error": 1.0, "factor_hit_rate": 0.5},
                         {"direction_hit": False, "abs_error": 3.0, "factor_hit_rate": 1.0}, {"direction_hit": None}])
    assert s == {"n_cases": 3, "n_judged": 2, "direction_hit_rate": 0.5, "mean_abs_error": 2.0, "factor_hit_rate": 0.75}
