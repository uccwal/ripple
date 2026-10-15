"""③ 과거 유사 국면: 시나리오 충격 벡터와 과거 horizon 구간의 실제 팩터 변화 벡터를 비교한다."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from ..config import DATA_DIR


@dataclass
class Regime:
    start: pd.Timestamp
    end: pd.Timestamp
    similarity: float
    factor_changes: dict[str, float]
    tag: str = ""
    tag_type: str = ""
    pnl: float = float("nan")
    asset_returns: dict[str, float] = field(default_factory=dict)


@lru_cache(maxsize=1)
def regime_tags() -> list[dict]:
    return json.loads((DATA_DIR / "regime_tags.json").read_text(encoding="utf-8"))["tags"]


def tag_for(start: pd.Timestamp, end: pd.Timestamp) -> tuple[str, str]:
    for t in regime_tags():
        d = pd.Timestamp(t["date"])
        if start <= d <= end:
            return t["label"], t["type"]
    return "", ""


def windows_table(window_changes: pd.DataFrame, horizon: int, step: int = 5) -> pd.DataFrame:
    """step 영업일 간격으로 끝나는 horizon 구간들의 변화 벡터 (NaN 없는 구간만)."""
    w = window_changes.dropna()
    if w.empty:
        return w
    # 가장 최근 구간부터 step 간격으로 뽑는다.
    return w.iloc[::-1].iloc[::step].iloc[::-1]


def similarity_scores(windows: pd.DataFrame, shock: dict[str, float]) -> pd.Series:
    """표준화(z-score) 후 유사도. 충격 변수가 2개 이상이면 코사인 유사도, 1개면 거리 기반 커널."""
    keys = [k for k, v in shock.items() if k in windows.columns and abs(v) > 1e-12]
    if not keys:
        return pd.Series(dtype=float)
    std = windows[keys].std(ddof=0).replace(0, np.nan)
    z_w = (windows[keys] / std).fillna(0.0)  # 평균 대신 0을 기준점으로 둔다 (방향 비교)
    z_s = np.array([shock[k] for k in keys]) / std.fillna(1.0).to_numpy()
    if len(keys) >= 2:
        num = z_w.to_numpy() @ z_s
        den = np.linalg.norm(z_w.to_numpy(), axis=1) * np.linalg.norm(z_s)
        cos = np.divide(num, den, out=np.zeros_like(num), where=den > 0)
        # 크기까지 닮은 구간을 우선하도록 크기 비율 가중 (0~1)
        ratio = np.minimum(np.linalg.norm(z_w.to_numpy(), axis=1), np.linalg.norm(z_s)) / np.maximum(
            np.maximum(np.linalg.norm(z_w.to_numpy(), axis=1), np.linalg.norm(z_s)), 1e-12
        )
        score = cos * (0.75 + 0.25 * ratio)
    else:
        score = np.exp(-np.abs(z_w.to_numpy()[:, 0] - z_s[0]))
    return pd.Series(score, index=windows.index)


def top_regimes(
    window_changes: pd.DataFrame,
    shock: dict[str, float],
    horizon: int,
    top_n: int = 5,
    min_similarity: float = 0.3,
) -> list[Regime]:
    windows = windows_table(window_changes, horizon)
    scores = similarity_scores(windows, shock)
    if scores.empty:
        return []
    trading_days = window_changes.index
    picked: list[Regime] = []
    for end, s in scores.sort_values(ascending=False).items():
        if s < min_similarity or len(picked) >= top_n:
            break
        end_pos = trading_days.get_loc(end)
        start = trading_days[max(end_pos - horizon, 0)]
        if any(not (end <= r.start or start >= r.end) for r in picked):
            continue  # 겹치는 구간 제외
        label, ttype = tag_for(start, end)
        picked.append(
            Regime(start=start, end=end, similarity=float(s),
                   factor_changes={k: float(v) for k, v in windows.loc[end].items()}, tag=label, tag_type=ttype)
        )
    return picked


def historical_max(window_changes: pd.DataFrame) -> dict[str, float]:
    """팩터별 과거 horizon 구간 변화의 최대 절댓값."""
    return {k: float(window_changes[k].abs().max()) for k in window_changes.columns if window_changes[k].notna().any()}


def analog_changes(window_changes: pd.DataFrame, horizon: int, tag_type: str) -> list[dict]:
    """같은 유형으로 라벨된 과거 사건 직후 horizon 구간의 실제 팩터 변화 (Scenario Builder 근거)."""
    out = []
    idx = window_changes.index
    for t in regime_tags():
        if t["type"] != tag_type:
            continue
        d = pd.Timestamp(t["date"])
        pos = idx.searchsorted(d)
        if pos == 0 or pos + horizon - 1 >= len(idx):
            continue
        start, end = idx[pos - 1], idx[pos + horizon - 1]
        row = window_changes.loc[end]
        if row.isna().all():
            continue
        out.append({"label": t["label"], "date": t["date"], "start": start, "end": end,
                    "changes": {k: float(v) for k, v in row.items() if pd.notna(v)}})
    return out


def analog_summary(analogs: list[dict]) -> dict[str, dict]:
    """사례 목록 → 팩터별 {n, median, p25, p75, up_share(상승 비율), labels}. LLM 이 중앙값을 직접 계산하지 않도록 엔진이 만든다."""
    by_factor: dict[str, list[float]] = {}
    for a in analogs:
        for k, v in a["changes"].items():
            by_factor.setdefault(k, []).append(float(v))
    out: dict[str, dict] = {}
    for k, vals in by_factor.items():
        arr = np.array(vals)
        out[k] = {
            "n": int(len(arr)),
            "median": float(np.median(arr)),
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
            "up_share": float((arr > 0).mean()),
        }
    return out
