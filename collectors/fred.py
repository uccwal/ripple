"""FRED (Federal Reserve Bank of St. Louis) 수집기.

    PYTHONPATH=backend:. python -m collectors.fred --since 2015-01-01

수집 시리즈 (제3자 저작권이 없는 미국 정부 공개 통계만):
- DGS10      → series_id DGS10  미국 국채 10년 금리 (%)      원 출처 Board of Governors of the Federal Reserve System (H.15)
- DCOILWTICO → series_id WTI    WTI 유가 (USD/bbl)           원 출처 U.S. Energy Information Administration (EIA)

수집하지 않는 것: S&P 500(SP500), 나스닥, 다우 등 제3자 저작권이 표시된 주가지수 시리즈.
FRED 는 이들 시리즈에 저작권자(S&P Dow Jones Indices 등)의 이용 제한을 표시하며, 설계서(4장)는
해외 주식 노출을 국내 상장 해외지수 ETF(krx_prices.py 의 US_EQ, US_TECH)로 대신하도록 정했다.

API: https://api.stlouisfed.org/fred/series/observations?series_id=…&api_key=…&file_type=json
     결측값은 문자열 "." 으로 오며 버린다. 응답 예: {"count": 2, "observations": [{"date": "2024-01-02", "value": "3.95"}, …]}
라이선스: FRED Terms of Use (https://fred.stlouisfed.org/legal/) — 출처 표시, 재배포 시 FRED·원 기관 표기.

주의: 이 모듈은 네트워크가 차단된 환경에서 작성되어 실제 호출을 검증하지 못했다. FRED_API_KEY 를 넣고 스모크 테스트할 것.
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings

from . import base
from .base import CollectorError, DateRange, MissingApiKey, UpsertResult

log = logging.getLogger("collectors.fred")

REQUIRED_KEY = "fred_api_key"  # app.config.settings 의 속성 이름 (환경 변수 FRED_API_KEY)
DEFAULT_SINCE = date(2015, 1, 1)
BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
SOURCE = "FRED (Federal Reserve Bank of St. Louis)"
PAGE_LIMIT = 100_000  # FRED 최대 limit


@dataclass(frozen=True)
class FredSpec:
    series_id: str  # RIPPLE series_id
    fred_id: str  # FRED series id
    name: str
    unit: str
    license: str
    origin: str  # 원 출처 기관


_FRED_TERMS = "FRED Terms of Use (https://fred.stlouisfed.org/legal/) — 출처 표시"

# 편집 가능한 매핑 표. 제3자 저작권 시리즈(SP500, NASDAQCOM, DJIA 등)는 추가하지 말 것.
SERIES: dict[str, FredSpec] = {
    "DGS10": FredSpec(
        series_id="DGS10", fred_id="DGS10", name="미국 국채 10년 금리", unit="%",
        origin="Board of Governors of the Federal Reserve System (H.15 Selected Interest Rates)",
        license=f"{_FRED_TERMS}; 원 자료는 미국 연방준비제도이사회 공개 데이터(public domain)"),
    "WTI": FredSpec(
        series_id="WTI", fred_id="DCOILWTICO", name="WTI 유가 (Cushing, OK 현물)", unit="USD/bbl",
        origin="U.S. Energy Information Administration (EIA)",
        license=f"{_FRED_TERMS}; 원 자료는 미국 에너지정보청(EIA) 공개 데이터(public domain)"),
    # 확장 후보 (설계서 표에 언급): 달러지수 DTWEXBGS (Board of Governors, public domain).
    # "DXY_BROAD": FredSpec("DXY_BROAD", "DTWEXBGS", "달러 인덱스 (광의, 명목)", "index",
    #                       origin="Board of Governors of the Federal Reserve System", license=_FRED_TERMS),
}


# ----------------------------------------------------------------------------
# 파싱 (HTTP 와 분리)
# ----------------------------------------------------------------------------

def parse_observations(payload: Any) -> list[tuple[date, float]]:
    """FRED observations JSON → [(date, value)]. "." 결측과 날짜 파싱 실패는 버린다."""
    if not isinstance(payload, dict):
        raise CollectorError(f"FRED 응답 형식이 아님: {type(payload).__name__}")
    if "error_message" in payload:
        raise CollectorError(f"FRED 오류 {payload.get('error_code')}: {payload['error_message']}")
    out: list[tuple[date, float]] = []
    for obs in payload.get("observations", []) or []:
        d = base.parse_date(obs.get("date"))
        v = base.to_float(obs.get("value"))
        if d is None or v is None:
            continue
        out.append((d, v))
    return out


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------

def fetch_observations(client: httpx.Client, api_key: str, fred_id: str, rng: DateRange) -> list[tuple[date, float]]:
    """observation_start/end 로 구간을 지정하고 offset 으로 페이지를 넘긴다 (일별 10년치도 1페이지면 충분)."""
    points: list[tuple[date, float]] = []
    offset = 0
    while True:
        params = {
            "series_id": fred_id, "api_key": api_key, "file_type": "json",
            "observation_start": rng.since.isoformat(), "observation_end": rng.until.isoformat(),
            "limit": PAGE_LIMIT, "offset": offset, "sort_order": "asc",
        }
        payload = base.get_json(client, BASE_URL, params)
        points.extend(parse_observations(payload))
        count = int(payload.get("count", 0) or 0)
        offset += int(payload.get("limit", PAGE_LIMIT) or PAGE_LIMIT)
        if offset >= count or not payload.get("observations"):
            break
    return points


def run(session: Session, rng: DateRange, *, api_key: str | None = None,
        client: httpx.Client | None = None, only: list[str] | None = None) -> dict[str, Any]:
    key = api_key or settings.fred_api_key
    if not key:
        raise MissingApiKey("FRED_API_KEY 가 없습니다 (https://fred.stlouisfed.org/docs/api/api_key.html 에서 발급)")
    own = client is None
    client = client or base.make_client()
    counts: dict[str, Any] = {}
    try:
        for sid, spec in SERIES.items():
            if only and sid not in only:
                continue
            pts = fetch_observations(client, key, spec.fred_id, rng)
            res: UpsertResult = base.upsert_series(
                session, series_id=spec.series_id, name=spec.name, source=SOURCE, unit=spec.unit, frequency="D",
                license=spec.license, source_url=f"https://fred.stlouisfed.org/series/{spec.fred_id}", points=pts)
            log.info("%s (%s, 원 출처 %s): %s", sid, spec.fred_id, spec.origin, res.as_dict())
            counts[sid] = res.total
    finally:
        if own:
            client.close()
    return counts


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    base.add_range_args(ap)
    ap.add_argument("--only", help="쉼표로 구분한 series_id (예: DGS10,WTI)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from app.db import init_db, session_scope

    init_db()
    rng = base.resolve_range(args.since, args.until, default_since=DEFAULT_SINCE)
    with session_scope() as s:
        counts = run(s, rng, only=args.only.split(",") if args.only else None)
    print(counts)


if __name__ == "__main__":
    main()
