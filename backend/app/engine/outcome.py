"""사후 검증과 포트폴리오 비교 (LLM 없음).

- actual_outcome: 이벤트 발표 전 마지막 거래일 종가 → horizon 영업일 뒤까지 실제 팩터 변화·자산 수익률·포트폴리오 손익.
  시나리오 충격값과 방향이 맞았는지(적중), 추정 손익과의 오차를 함께 돌려준다. 데이터가 horizon 에 못 미치면 잠정(complete=False).
- cross_portfolio: 같은 충격값을 다른 모델 포트폴리오에 적용한 손익 (유사 국면 계산은 생략).
"""
from __future__ import annotations

import math
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.tables import Holding, Portfolio
from .catalog import FACTOR_BY_ID, FACTORS
from .data import asset_returns, load_levels, required_series, window_return


def _sign(v: float | None) -> int | None:
    if v is None or (isinstance(v, float) and math.isnan(v)) or abs(v) < 1e-12:
        return None
    return 1 if v > 0 else -1


def actual_outcome(session: Session, holdings: list[Holding], announced_at: date, horizon: int,
                   shocks: dict[str, float], estimate_pnl: float | None) -> dict | None:
    """발표일(announced_at) 기준 실제 결과. 발표 전 마지막 거래일이 없거나 이후 거래일이 하나도 없으면 None."""
    sids = required_series(holdings)
    levels = load_levels(session, sids, None)
    if levels.empty:
        return None
    idx = levels.index
    pos0 = int(idx.searchsorted(pd.Timestamp(announced_at))) - 1  # 발표 전 마지막 거래일
    if pos0 < 0:
        return None
    end_pos = min(pos0 + horizon, len(idx) - 1)
    days = end_pos - pos0
    if days < 1:
        return None
    start, end = idx[pos0], idx[end_pos]

    factors: dict[str, dict] = {}
    hits = 0
    judged = 0
    for f in FACTORS:
        if f.series_id not in levels.columns:
            continue
        a, b = levels[f.series_id].iloc[pos0], levels[f.series_id].iloc[end_pos]
        if pd.isna(a) or pd.isna(b) or (f.transform == "pct" and a == 0):
            continue
        actual = float((b / a - 1) * 100) if f.transform == "pct" else float(b - a)
        shock = shocks.get(f.factor_id)
        hit = None
        if shock is not None and _sign(shock) is not None and _sign(actual) is not None:
            hit = _sign(shock) == _sign(actual)
            judged += 1
            hits += int(hit)
        factors[f.factor_id] = {"name": f.name, "unit": f.unit, "shock": shock, "actual": actual, "hit": hit}

    by_asset: dict[str, float | None] = {}
    for h in holdings:
        try:
            r = window_return(asset_returns(h, levels), start, end)
        except KeyError:
            r = float("nan")
        by_asset[h.asset_id] = None if math.isnan(r) else r
    pnl = (float(sum(h.weight / 100 * by_asset[h.asset_id] for h in holdings))
           if all(v is not None for v in by_asset.values()) else None)
    est_sign, act_sign = _sign(estimate_pnl), _sign(pnl)
    return {
        "start": start.date().isoformat(), "end": end.date().isoformat(), "days": int(days), "horizon": horizon,
        "complete": days >= horizon,
        "factors": factors,
        "factor_hit_rate": (hits / judged) if judged else None, "factors_judged": judged,
        "by_asset": by_asset,
        "portfolio_pnl": pnl,
        "estimate_pnl": estimate_pnl,
        "direction_hit": (est_sign == act_sign) if (est_sign is not None and act_sign is not None) else None,
        "abs_error": (abs(estimate_pnl - pnl) if (estimate_pnl is not None and pnl is not None) else None),
    }


def cross_portfolio(session: Session, current_portfolio_id: str, as_of: date, horizon: int,
                    shocks: dict[str, float], run_id: str) -> list[dict]:
    """다른 모델 포트폴리오에 같은 충격값을 적용한 손익. 계산 불가(시계열 부족)면 error 를 적고 넘어간다."""
    from .risk import compute, prepare  # noqa: PLC0415 (순환 참조 회피)

    rows: list[dict] = []
    for pf in session.scalars(select(Portfolio).order_by(Portfolio.portfolio_id)):
        if pf.portfolio_id == current_portfolio_id:
            continue
        try:
            ctx = prepare(session, pf.portfolio_id, as_of, horizon)
            out = compute(ctx, shocks, [], run_id)
        except ValueError as e:
            rows.append({"portfolio_id": pf.portfolio_id, "name": pf.name, "aum": pf.aum, "pnl": None, "amount": None,
                         "range": None, "worst_asset": None, "worst_contribution": None, "current": False, "error": str(e)})
            continue
        r = out["result"]
        worst = next((a for a in r["by_asset"] if a["asset_id"] == (r["top_contributors"][0] if r["top_contributors"] else None)), None)
        rows.append({"portfolio_id": pf.portfolio_id, "name": pf.name, "aum": pf.aum, "pnl": r["portfolio_pnl"],
                     "amount": r["pnl_amount"], "range": r["range"],
                     "worst_asset": worst["name"] if worst else None,
                     "worst_contribution": worst["contribution"] if worst else None, "current": False, "error": None})
    return rows
