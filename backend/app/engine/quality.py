"""시계열 신선도·커버리지 판정 (데이터 관리 화면·레이더)."""
from __future__ import annotations

from datetime import date

import numpy as np

# 값이 가끔만 바뀌는 계단형 시계열 (기준금리). 커버리지·지연 판정을 완화한다.
STEP_SERIES = {"BOK_BASE_RATE", "FED_TARGET_UPPER"}
STALE_BDAYS = 5  # 최종 관측일이 오늘보다 이 영업일 이상 뒤처지면 '지연' (공표 지연 1~2일은 정상)
# 원 기관의 공표 주기가 긴 시리즈는 허용 지연을 늘린다. WTI(EIA)는 FRED 에 주 1회 반영되어 최대 7~8영업일 뒤처진다.
STALE_TOLERANCE = {"WTI": 10}
MIN_COVERAGE = 0.85  # 기간 내 영업일 대비 관측 비율이 이보다 낮으면 '결측 많음' (한국·미국 휴장일 차이 ≈ 5%)


def series_quality(series_id: str, count: int, first: date | None, last: date | None, today: date, synthetic: bool) -> dict:
    """신선도·커버리지 지표. stale_bdays: 최종 관측일 이후 영업일 수, coverage: 관측 수 / 기간 영업일 수."""
    if not count or first is None or last is None:
        return {"stale_bdays": None, "coverage": None, "quality": "empty"}
    step_like = series_id in STEP_SERIES
    stale_limit = STALE_TOLERANCE.get(series_id, STALE_BDAYS)
    stale = int(np.busday_count(last, today)) if last < today else 0
    bdays = int(np.busday_count(first, last)) + 1
    coverage = round(min(count / bdays, 1.0), 3) if bdays > 0 else None
    if synthetic:
        quality = "synthetic"
    elif stale > stale_limit and not step_like:
        quality = "stale"
    elif coverage is not None and coverage < MIN_COVERAGE and not step_like:
        quality = "gappy"
    elif step_like and stale > 20:
        quality = "stale"
    else:
        quality = "ok"
    return {"stale_bdays": stale, "coverage": coverage, "quality": quality}
