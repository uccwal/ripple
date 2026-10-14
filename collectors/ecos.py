"""한국은행 경제통계시스템(ECOS) OpenAPI 수집기.

    PYTHONPATH=backend:. python -m collectors.ecos --since 2015-01-01

수집 시리즈
- 원/달러 환율 (매매기준율, 일별)  → USDKRW  (KRW)
- 국고채 3년 금리 (시장금리, 일별)   → KTB3Y   (%)
- (선택) 한국은행 기준금리 (일별)    → BOK_BASE_RATE (%)  — 팩터 카탈로그에는 없고 이벤트 검증·화면 참고용

API 형식
  https://ecos.bok.or.kr/api/StatisticSearch/{인증키}/json/kr/{시작행}/{끝행}/{통계표코드}/{주기}/{검색시작일}/{검색종료일}/{통계항목코드1}
  주기 D 의 날짜는 YYYYMMDD. 정상 응답: {"StatisticSearch": {"list_total_count": N, "row": [{"TIME": "20240102", "DATA_VALUE": "1300.4", …}]}}
  오류 응답:  {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}  (INFO-200 은 '데이터 없음' 이라 빈 결과로 처리)
라이선스: 한국은행 ECOS 이용약관 — 출처(한국은행 경제통계시스템) 표시.

주의: 네트워크가 차단된 환경에서 작성되어 실제 호출을 검증하지 못했다. ECOS_API_KEY 를 넣고 스모크 테스트할 것.
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
from .base import CollectorError, DateRange, MissingApiKey

log = logging.getLogger("collectors.ecos")

REQUIRED_KEY = "ecos_api_key"  # 환경 변수 ECOS_API_KEY
DEFAULT_SINCE = date(2015, 1, 1)
BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
SOURCE = "한국은행 ECOS"
LICENSE = "한국은행 경제통계시스템(ECOS) OpenAPI 이용약관 — 출처 표시 (한국은행 ECOS)"
PAGE_SIZE = 10_000  # 한 번에 받는 최대 행 수


@dataclass(frozen=True)
class EcosSpec:
    series_id: str
    stat_code: str  # 통계표 코드
    item_code: str  # 통계항목 코드1
    cycle: str  # D 일별
    name: str
    unit: str
    optional: bool = False  # True 면 실패해도 경고만 남기고 계속


# ============================================================================
# 통계표·항목 코드 표 — 반드시 ECOS 「통계코드검색」(https://ecos.bok.or.kr/api/#/DevGuide/StatisticalCodeSearch)
# 에서 확인할 것. 아래 코드는 공개 문서 기준으로 적었지만 이 샌드박스에서는 실제 조회로 검증하지 못했다.
#   731Y001 주요국 통화의 대원화 환율       0000001 원/미국달러(매매기준율)
#   817Y002 시장금리(일별)                 010200000 국고채(3년)
#   722Y001 한국은행 기준금리 및 여수신금리  0101000 한국은행 기준금리
# ============================================================================
SERIES: dict[str, EcosSpec] = {
    "USDKRW": EcosSpec("USDKRW", "731Y001", "0000001", "D", "원/달러 환율 (매매기준율)", "KRW"),
    "KTB3Y": EcosSpec("KTB3Y", "817Y002", "010200000", "D", "국고채 3년 금리", "%"),
    "BOK_BASE_RATE": EcosSpec("BOK_BASE_RATE", "722Y001", "0101000", "D", "한국은행 기준금리", "%", optional=True),
}


# ----------------------------------------------------------------------------
# 파싱 (HTTP 와 분리)
# ----------------------------------------------------------------------------

def parse_statistic_search(payload: Any) -> tuple[list[tuple[date, float]], int]:
    """ECOS StatisticSearch JSON → ([(date, value)], list_total_count).

    - RESULT.CODE 가 INFO-200(데이터 없음) 이면 빈 결과, 그 밖의 RESULT 는 오류.
    - DATA_VALUE 가 비었거나 숫자가 아니면 버린다.
    """
    if not isinstance(payload, dict):
        raise CollectorError(f"ECOS 응답 형식이 아님: {type(payload).__name__}")
    if "RESULT" in payload:
        code = str(payload["RESULT"].get("CODE", ""))
        msg = payload["RESULT"].get("MESSAGE", "")
        if code == "INFO-200":
            return [], 0
        raise CollectorError(f"ECOS 오류 {code}: {msg}")
    body = payload.get("StatisticSearch")
    if not isinstance(body, dict):
        raise CollectorError(f"ECOS 응답에 StatisticSearch 가 없음: {list(payload)[:5]}")
    total = int(body.get("list_total_count", 0) or 0)
    out: list[tuple[date, float]] = []
    for row in body.get("row", []) or []:
        d = base.parse_date(row.get("TIME"))
        v = base.to_float(row.get("DATA_VALUE"))
        if d is None or v is None:
            continue
        out.append((d, v))
    return out, total


def build_url(api_key: str, spec: EcosSpec, start_row: int, end_row: int, rng: DateRange) -> str:
    return (f"{BASE_URL}/{api_key}/json/kr/{start_row}/{end_row}/{spec.stat_code}/{spec.cycle}/"
            f"{base.yyyymmdd(rng.since)}/{base.yyyymmdd(rng.until)}/{spec.item_code}")


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------

def fetch_series(client: httpx.Client, api_key: str, spec: EcosSpec, rng: DateRange) -> list[tuple[date, float]]:
    points: list[tuple[date, float]] = []
    start = 1
    while True:
        url = build_url(api_key, spec, start, start + PAGE_SIZE - 1, rng)
        payload = base.get_json(client, url)
        rows, total = parse_statistic_search(payload)
        points.extend(rows)
        start += PAGE_SIZE
        if start > total or not rows:
            break
    return points


def run(session: Session, rng: DateRange, *, api_key: str | None = None,
        client: httpx.Client | None = None, only: list[str] | None = None) -> dict[str, Any]:
    key = api_key or settings.ecos_api_key
    if not key:
        raise MissingApiKey("ECOS_API_KEY 가 없습니다 (https://ecos.bok.or.kr/api/ 에서 인증키 신청)")
    own = client is None
    client = client or base.make_client()
    counts: dict[str, Any] = {}
    try:
        for sid, spec in SERIES.items():
            if only and sid not in only:
                continue
            try:
                pts = fetch_series(client, key, spec, rng)
            except CollectorError as exc:
                if spec.optional:
                    log.warning("%s (선택 시리즈) 건너뜀: %s", sid, exc)
                    counts[sid] = 0
                    continue
                raise
            res = base.upsert_series(
                session, series_id=spec.series_id, name=spec.name, source=SOURCE, unit=spec.unit, frequency="D",
                license=LICENSE,
                source_url=f"https://ecos.bok.or.kr/#/SearchStat (통계표 {spec.stat_code}, 항목 {spec.item_code})",
                points=pts)
            log.info("%s (%s/%s): %s", sid, spec.stat_code, spec.item_code, res.as_dict())
            counts[sid] = res.total
    finally:
        if own:
            client.close()
    return counts


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    base.add_range_args(ap)
    ap.add_argument("--only", help="쉼표로 구분한 series_id (예: USDKRW,KTB3Y)")
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
