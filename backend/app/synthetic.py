"""데모용 합성 시계열.

실제 수집기(collectors/)를 API 키와 함께 실행하기 전에도 앱 전체 흐름을 시연할 수 있도록 만든다.
- 모든 시리즈의 source는 "SYNTHETIC"으로 저장되고, 화면 상단에 '합성 데이터' 배지가 표시된다.
- 변동성·상관관계는 실제 시장과 비슷한 크기로 정했지만 실제 값이 아니다.
- regime_tags.json의 사건 일자 직후에는 사건 유형별 '양식화된' 충격을 넣어 유사 국면 탐색을 시연할 수 있게 했다.
  이 충격의 방향은 일반적인 시장 반응을 따르지만 크기는 실제 기록이 아니다.
실제 데이터가 수집되면 같은 series_id의 값을 덮어쓴다.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .config import DATA_DIR

START, END = "2015-01-02", "2026-10-13"
SYNTHETIC_LICENSE = "합성 데이터 — 실제 시장 데이터가 아님. 시연용으로 생성 (backend/app/synthetic.py, seed=42)"

# (series_id, 이름, 단위, 시작값)
FACTOR_SPECS = [
    ("USDKRW", "원/달러 환율 (합성)", "KRW", 1170.0),
    ("KOSPI", "KOSPI 지수 (합성)", "index", 1930.0),
    ("KOSPI_IT", "KOSPI IT 업종 지수 (합성)", "index", 1000.0),
    ("US_EQ", "미국 주식 지수 대리 (합성)", "index", 2050.0),
    ("DGS10", "미국 국채 10년 금리 (합성)", "%", 2.1),
    ("KTB3Y", "국고채 3년 금리 (합성)", "%", 2.1),
    ("WTI", "WTI 유가 (합성)", "USD/bbl", 53.0),
    ("DGS2", "미국 국채 2년 금리 (합성)", "%", 0.7),
    ("DXY_BROAD", "달러 인덱스 광의 (합성)", "index", 105.0),
]
ASSET_SPECS = [
    ("KR_SEMI", "국내 반도체 대형주 가격 지수 (합성)", "index", 100.0),
    ("KR_K200", "KOSPI 200 가격 지수 (합성)", "index", 100.0),
    ("KR_AUTO", "국내 자동차 업종 가격 지수 (합성)", "index", 100.0),
    ("US_TECH", "미국 기술주 지수 (합성)", "index", 100.0),
]

# 일별 변동성: % 변화율 팩터는 %, 금리는 %p
VOL = {"USDKRW": 0.45, "KOSPI": 1.0, "KOSPI_IT": 1.45, "US_EQ": 1.0, "DGS10": 0.060, "KTB3Y": 0.030, "WTI": 2.3,
       "DGS2": 0.055, "DXY_BROAD": 0.30}
ORDER = ["USDKRW", "KOSPI", "KOSPI_IT", "US_EQ", "DGS10", "KTB3Y", "WTI", "DGS2", "DXY_BROAD"]
CORR = np.array([
    #  FX     KOSPI  IT     USEQ   DGS10  KTB    WTI    DGS2   DXY
    [1.00, -0.45, -0.40, -0.20, 0.00, 0.05, -0.15, 0.05, 0.70],
    [-0.45, 1.00, 0.85, 0.40, 0.10, 0.05, 0.20, 0.05, -0.35],
    [-0.40, 0.85, 1.00, 0.45, 0.05, 0.00, 0.10, 0.00, -0.30],
    [-0.20, 0.40, 0.45, 1.00, 0.20, 0.05, 0.25, 0.15, -0.25],
    [0.00, 0.10, 0.05, 0.20, 1.00, 0.45, 0.20, 0.85, 0.15],
    [0.05, 0.05, 0.00, 0.05, 0.45, 1.00, 0.10, 0.40, 0.05],
    [-0.15, 0.20, 0.10, 0.25, 0.20, 0.10, 1.00, 0.15, -0.30],
    [0.05, 0.05, 0.00, 0.15, 0.85, 0.40, 0.15, 1.00, 0.25],
    [0.70, -0.35, -0.30, -0.25, 0.15, 0.05, -0.30, 0.25, 1.00],
])
# 사건 유형별 양식화된 20영업일 누적 충격 (방향 위주, 크기는 가정)
EPISODE = {
    "tariff": {"USDKRW": 3.0, "KOSPI": -5.0, "KOSPI_IT": -8.5, "US_EQ": -4.5, "DGS10": -0.20, "KTB3Y": -0.06, "WTI": -6.0,
               "DGS2": -0.15, "DXY_BROAD": 2.0},
    "regulation": {"USDKRW": 2.0, "KOSPI": -4.0, "KOSPI_IT": -7.0, "US_EQ": -0.5, "DGS10": -0.05, "KTB3Y": -0.04, "WTI": -1.0,
                   "DGS2": -0.03, "DXY_BROAD": 0.5},
    "rate": {"USDKRW": 2.5, "KOSPI": -4.0, "KOSPI_IT": -5.5, "US_EQ": -4.0, "DGS10": 0.35, "KTB3Y": 0.18, "WTI": -3.0,
             "DGS2": 0.45, "DXY_BROAD": 2.5},
    "fx": {"USDKRW": 3.5, "KOSPI": -5.5, "KOSPI_IT": -6.5, "US_EQ": -5.0, "DGS10": -0.15, "KTB3Y": -0.05, "WTI": -7.0,
           "DGS2": -0.10, "DXY_BROAD": 3.0},
    "macro": {"USDKRW": 4.0, "KOSPI": -8.0, "KOSPI_IT": -10.0, "US_EQ": -9.0, "DGS10": -0.40, "KTB3Y": -0.15, "WTI": -15.0,
              "DGS2": -0.50, "DXY_BROAD": 4.0},
}


def generate(seed: int = 42) -> dict[str, pd.Series]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(START, END)
    n = len(dates)
    vol = np.array([VOL[k] for k in ORDER])
    cov = CORR * np.outer(vol, vol)
    # 두꺼운 꼬리: t분포(자유도 5)로 스케일
    z = rng.multivariate_normal(np.zeros(len(ORDER)), cov, size=n)
    t_scale = np.sqrt(3 / 5) * np.sqrt(5 / rng.chisquare(5, size=(n, 1)))
    shocks = pd.DataFrame(z * t_scale, index=dates, columns=ORDER)
    # 장기 추세 (연율): 주식 상승, 금리 사이클
    drift = {"KOSPI": 4.0, "KOSPI_IT": 8.0, "US_EQ": 9.0, "WTI": 1.0, "USDKRW": 1.0}
    for k, a in drift.items():
        shocks[k] += a / 252

    tags = json.loads((DATA_DIR / "regime_tags.json").read_text(encoding="utf-8"))["tags"]
    for t in tags:
        pos = dates.searchsorted(pd.Timestamp(t["date"]))
        if pos >= n:
            continue
        scale = rng.uniform(0.7, 1.3)
        span = min(20, n - pos)
        for k, total in EPISODE[t["type"]].items():
            shocks.iloc[pos:pos + span, shocks.columns.get_loc(k)] += total * scale / 20

    out: dict[str, pd.Series] = {}
    start = {s[0]: s[3] for s in FACTOR_SPECS}
    for k in ORDER:
        if k in ("DGS10", "KTB3Y", "DGS2"):
            # 평균 회귀하는 금리 (하한 0.2%)
            level = np.empty(n)
            level[0] = start[k]
            target = {"DGS10": 2.6, "KTB3Y": 2.4, "DGS2": 2.2}[k]
            for i in range(1, n):
                level[i] = max(0.2, level[i - 1] + shocks[k].iloc[i] + 0.002 * (target - level[i - 1]))
            out[k] = pd.Series(level, index=dates)
        else:
            out[k] = pd.Series(start[k] * np.cumprod(1 + shocks[k].to_numpy() / 100), index=dates)

    f = shocks
    noise = lambda s: rng.normal(0, s, n)  # noqa: E731
    asset_ret = {
        "KR_SEMI": 1.10 * f["KOSPI_IT"] + noise(1.1),
        "KR_K200": 1.00 * f["KOSPI"] + noise(0.45),
        "KR_AUTO": 0.90 * f["KOSPI"] + 0.20 * f["USDKRW"] + noise(1.0),
        "US_TECH": 1.25 * f["US_EQ"] + 0.15 * f["KOSPI_IT"] + noise(0.6),
    }
    for k, r in asset_ret.items():
        out[k] = pd.Series(100 * np.cumprod(1 + np.asarray(r) / 100), index=dates)
    return out
