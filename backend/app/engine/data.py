"""DB의 시계열을 계산용 표로 읽어 온다. 모든 함수는 as_of 이후 데이터를 쓰지 않는다 (시점 필터)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.tables import Holding, Series, SeriesValue
from .catalog import FACTORS

SYNTHETIC_SOURCE = "SYNTHETIC"


@dataclass
class SeriesMeta:
    series_id: str
    name: str
    source: str
    license: str
    source_url: str
    last_date: date | None
    collected_at: datetime | None

    @property
    def synthetic(self) -> bool:
        return self.source.startswith(SYNTHETIC_SOURCE)


def load_levels(session: Session, series_ids: list[str], as_of: date | None = None) -> pd.DataFrame:
    """series_id별 일별 값(level)을 열로 갖는 DataFrame. 날짜 오름차순."""
    q = select(SeriesValue.series_id, SeriesValue.date, SeriesValue.value).where(SeriesValue.series_id.in_(series_ids))
    if as_of is not None:
        q = q.where(SeriesValue.date <= as_of)
    rows = session.execute(q).all()
    if not rows:
        return pd.DataFrame(columns=series_ids, dtype=float)
    df = pd.DataFrame(rows, columns=["series_id", "date", "value"])
    wide = df.pivot_table(index="date", columns="series_id", values="value", aggfunc="last").sort_index()
    wide.index = pd.to_datetime(wide.index)
    return wide.reindex(columns=series_ids)


def series_meta(session: Session, series_ids: list[str]) -> dict[str, SeriesMeta]:
    out: dict[str, SeriesMeta] = {}
    for s in session.scalars(select(Series).where(Series.series_id.in_(series_ids))):
        last = session.execute(
            select(SeriesValue.date, SeriesValue.collected_at)
            .where(SeriesValue.series_id == s.series_id)
            .order_by(SeriesValue.date.desc())
            .limit(1)
        ).first()
        out[s.series_id] = SeriesMeta(
            s.series_id, s.name, s.source, s.license, s.source_url,
            last[0] if last else None, last[1] if last else None,
        )
    return out


def factor_returns(levels: pd.DataFrame) -> pd.DataFrame:
    """팩터 일별 변화: unit '%'는 변화율×100, '%p'는 차분."""
    cols = {}
    for f in FACTORS:
        if f.series_id not in levels:
            continue
        s = levels[f.series_id]
        cols[f.factor_id] = s.pct_change(fill_method=None) * 100 if f.transform == "pct" else s.diff()
    return pd.DataFrame(cols)


def factor_window_changes(levels: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """각 날짜에서 끝나는 horizon 영업일 누적 변화 (unit 규칙은 factor_returns와 같음)."""
    cols = {}
    for f in FACTORS:
        if f.series_id not in levels:
            continue
        s = levels[f.series_id]
        cols[f.factor_id] = (s / s.shift(horizon) - 1) * 100 if f.transform == "pct" else s - s.shift(horizon)
    return pd.DataFrame(cols)


def asset_returns(holding: Holding, levels: pd.DataFrame) -> pd.Series:
    """자산의 USD 기준 일별 수익률(%)."""
    pricing = holding.pricing or {}
    if "series_id" in pricing:
        local_ret = levels[pricing["series_id"]].pct_change(fill_method=None)
    else:
        y = levels[pricing["yield_series"]]
        dur = float(pricing["duration"])
        local_ret = (y.shift(1) / 100 / 252) - dur * (y.diff() / 100)
    if holding.currency == "KRW":
        fx = levels["USDKRW"].pct_change(fill_method=None)
        local_ret = (1 + local_ret) / (1 + fx) - 1
    return local_ret * 100


def required_series(holdings: list[Holding]) -> list[str]:
    ids = {f.series_id for f in FACTORS}
    for h in holdings:
        p = h.pricing or {}
        ids.add(p.get("series_id") or p.get("yield_series"))
    return sorted(i for i in ids if i)


def window_return(daily_pct: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """(start, end] 구간 누적 수익률(%)."""
    seg = daily_pct[(daily_pct.index > start) & (daily_pct.index <= end)].dropna() / 100
    return float((np.prod(1 + seg) - 1) * 100) if len(seg) else float("nan")
