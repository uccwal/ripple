"""① 팩터 민감도 추정: r_{i,t} = α_i + Σ_k β_{i,k} f_{k,t} + ε_{i,t} (OLS)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BetaFit:
    asset_id: str
    betas: dict[str, float]
    std_err: dict[str, float]
    alpha: float
    r2: float
    n_obs: int
    window_start: pd.Timestamp
    window_end: pd.Timestamp


def ols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """절편을 포함한 OLS. (계수, 표준오차, R²) — 계수[0]은 절편."""
    n = len(y)
    Xc = np.column_stack([np.ones(n), X])
    coef, *_ = np.linalg.lstsq(Xc, y, rcond=None)
    resid = y - Xc @ coef
    dof = max(n - Xc.shape[1], 1)
    sigma2 = float(resid @ resid) / dof
    cov = sigma2 * np.linalg.pinv(Xc.T @ Xc)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(resid @ resid) / ss_tot if ss_tot > 0 else 0.0
    return coef, se, r2


def fit_asset(
    asset_id: str,
    asset_ret: pd.Series,
    factor_ret: pd.DataFrame,
    factor_ids: list[str],
    window_days: int,
    min_obs: int,
) -> BetaFit:
    data = pd.concat([asset_ret.rename("_y"), factor_ret[factor_ids]], axis=1).dropna().tail(window_days)
    if len(data) < min_obs:
        raise ValueError(f"{asset_id}: 회귀 관측치 부족 ({len(data)} < {min_obs})")
    coef, se, r2 = ols(data["_y"].to_numpy(), data[factor_ids].to_numpy())
    return BetaFit(
        asset_id=asset_id,
        betas={k: float(coef[i + 1]) for i, k in enumerate(factor_ids)},
        std_err={k: float(se[i + 1]) for i, k in enumerate(factor_ids)},
        alpha=float(coef[0]),
        r2=float(r2),
        n_obs=len(data),
        window_start=data.index[0],
        window_end=data.index[-1],
    )
