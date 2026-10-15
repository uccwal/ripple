"""공공데이터포털 금융위원회 시세정보 API 수집기 (국내 지수·국내 상장 ETF).

    PYTHONPATH=backend:. python -m collectors.krx_prices --since 2015-01-01

사용하는 API (모두 공공데이터포털 '금융위원회' 제공, 서비스키 1개로 공통 사용)
- 지수시세정보     GetMarketIndexInfoService_V2/getStockMarketIndex_V2     → KOSPI, KOSPI_IT, KR_K200
- 증권상품시세정보 GetSecuritiesProductInfoService_V2/getETFPriceInfo_V2    → US_EQ, US_TECH, KR_SEMI, KR_AUTO (국내 상장 ETF 종가)
- 주식시세정보     GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2    → (개별 종목이 필요할 때; 기본 매핑에는 없음)

설계 원칙 (docs/DESIGN.md 4장): 해외 주식 노출은 S&P 500 등 제3자 저작권 지수 대신 국내 상장 해외지수 ETF 로 대리한다.
따라서 US_EQ 는 S&P 500 지수가 아니라 국내 상장 S&P 500 ETF 의 원화 종가(환헤지 없음 → 환율 효과가 포함됨)이다.
이 한계는 data/SOURCES.md 에 기재한다.

응답 형식 (resultType=json)
  {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                "body": {"numOfRows": 1000, "pageNo": 1, "totalCount": 2500,
                         "items": {"item": [{"basDt": "20240102", "idxNm": "코스피", "clpr": "2669.81", …}]}}}}
  항목이 1건이면 item 이 dict 로, 0건이면 items 가 "" 로 올 수 있어 모두 처리한다.
  키 오류 등은 JSON 대신 XML(<OpenAPI_ServiceResponse>…<returnAuthMsg>…) 로 오므로 그것도 파싱해 메시지를 보여준다.
라이선스: 공공데이터포털 이용허락범위 — API 마다 다르므로(공공누리 유형 또는 '이용허락범위 제한 없음') 활용신청 화면에서
  각 API 의 이용허락범위를 확인하고 아래 LICENSE 문자열을 그에 맞게 수정할 것. 출처(금융위원회·공공데이터포털) 표시.

주의: 네트워크가 차단된 환경에서 작성되어 실제 호출을 검증하지 못했다. DATA_GO_KR_API_KEY 를 넣고 스모크 테스트할 것.
"""
from __future__ import annotations

import argparse
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any
from urllib.parse import unquote

import httpx
from sqlalchemy.orm import Session

from app.config import settings

from . import base
from .base import CollectorError, DateRange, MissingApiKey

log = logging.getLogger("collectors.krx_prices")

REQUIRED_KEY = "data_go_kr_api_key"  # 환경 변수 DATA_GO_KR_API_KEY
DEFAULT_SINCE = date(2015, 1, 1)
HOST = "https://apis.data.go.kr/1160100"
# 2026년 현재 포털은 V2 엔드포인트를 제공한다 (활용신청 화면의 End Point 기준). 키는 신청한 버전에만 등록된다.
ENDPOINTS = {
    "index": f"{HOST}/GetMarketIndexInfoService_V2/getStockMarketIndex_V2",
    "etf": f"{HOST}/GetSecuritiesProductInfoService_V2/getETFPriceInfo_V2",
    "stock": f"{HOST}/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2",
}
SOURCE = "공공데이터포털 · 금융위원회 시세정보 (KRX 원천)"
# ★ 활용신청 시 확인한 각 API 의 이용허락범위로 수정할 것 (예: "공공누리 제1유형", "이용허락범위 제한 없음").
LICENSE = ("공공데이터포털 이용허락범위 (API별 확인 필요: 금융위원회 지수시세정보·증권상품시세정보) — "
           "출처 표시 (금융위원회, 공공데이터포털). 원천 데이터는 한국거래소(KRX).")
PAGE_SIZE = 1000


@dataclass(frozen=True)
class KrxSpec:
    series_id: str
    kind: str  # index | etf | stock
    name: str  # 저장할 시리즈 이름
    unit: str
    match_name: str = ""  # index: idxNm 정확히 일치 / etf·stock: itmsNm (참고용, 코드 없을 때 사용)
    code: str = ""  # etf·stock: 단축코드(srtnCd). 있으면 likeSrtnCd 로 조회 (이름 변경에 강함)
    note: str = ""
    alt_names: tuple[str, ...] = ()  # index: match_name 으로 0건이면 차례로 시도할 다른 지수명
    fallback: str = ""  # 모두 실패하면 이 series_id(SERIES 의 다른 항목)의 데이터를 대리로 저장
    optional: bool = False  # True 면 0건이어도 오류·빈 시리즈를 만들지 않고 건너뛴다 (업종지수 확장분)


# ============================================================================
# 이름·코드 매핑 표 (편집 가능). 지수명·ETF 명은 KRX 개편으로 바뀔 수 있으므로 첫 실행 로그에서 매칭 결과를 확인할 것.
#  - 지수 조회는 idxNm 정확 일치. KRX 업종지수 개편으로 "코스피 전기전자" 가 다른 이름일 수 있음 (예: "코스피 전기·전자", "KOSPI 200 정보기술").
#  - ETF 는 단축코드로 조회한다. 코드 변경·상장폐지 시 교체.
# ============================================================================
SERIES: dict[str, KrxSpec] = {
    "KOSPI": KrxSpec("KOSPI", "index", "KOSPI 지수", "index", match_name="코스피"),
    "KOSPI_IT": KrxSpec("KOSPI_IT", "index", "KOSPI 전기전자 업종지수", "index", match_name="코스피 전기전자",
                        note="업종지수 명칭은 ECOS·KRX 개편 시 확인",
                        alt_names=("코스피 전기·전자", "코스피 전기,전자", "코스피200 정보기술", "코스피 200 정보기술",
                                   "KOSPI 200 정보기술", "코스피 200 IT", "코스피200 IT", "코스피 전기전자업", "코스피 IT"),
                        fallback="KR_SEMI"),
    "KR_K200": KrxSpec("KR_K200", "index", "KOSPI 200 지수", "index", match_name="코스피 200"),
    "US_EQ": KrxSpec("US_EQ", "etf", "TIGER 미국S&P500 ETF 종가 (S&P 500 대리, KRW·환노출)", "KRW",
                     match_name="TIGER 미국S&P500", code="360750"),
    "US_TECH": KrxSpec("US_TECH", "etf", "TIGER 미국나스닥100 ETF 종가 (나스닥 100 대리, KRW·환노출)", "KRW",
                       match_name="TIGER 미국나스닥100", code="133690"),
    "KR_SEMI": KrxSpec("KR_SEMI", "etf", "KODEX 반도체 ETF 종가", "KRW", match_name="KODEX 반도체", code="091160"),
    "KR_AUTO": KrxSpec("KR_AUTO", "etf", "KODEX 자동차 ETF 종가", "KRW", match_name="KODEX 자동차", code="091180"),
    # ---- 확장 (선택): 시장·업종 폭을 넓혀 과거 유사 국면·업종 노출 분석에 쓴다. 명칭이 바뀌면 alt_names 로 흡수.
    "KOSDAQ": KrxSpec("KOSDAQ", "index", "KOSDAQ 지수", "index", match_name="코스닥", optional=True),
    "K200_FIN": KrxSpec("K200_FIN", "index", "KOSPI 200 금융 업종지수", "index", match_name="코스피 200 금융",
                        alt_names=("코스피200 금융",), optional=True),
    "K200_IND": KrxSpec("K200_IND", "index", "KOSPI 200 산업재 업종지수", "index", match_name="코스피 200 산업재",
                        alt_names=("코스피200 산업재",), optional=True),
    "K200_ENE": KrxSpec("K200_ENE", "index", "KOSPI 200 에너지·화학 업종지수", "index", match_name="코스피 200 에너지/화학",
                        alt_names=("코스피 200 에너지화학", "코스피200 에너지/화학"), optional=True),
    "K200_CD": KrxSpec("K200_CD", "index", "KOSPI 200 경기소비재 업종지수 (자동차 포함)", "index", match_name="코스피 200 경기소비재",
                       alt_names=("코스피 200 자유소비재", "코스피200 경기소비재"), optional=True),
    "K200_MAT": KrxSpec("K200_MAT", "index", "KOSPI 200 철강·소재 업종지수", "index", match_name="코스피 200 철강/소재",
                        alt_names=("코스피 200 철강소재", "코스피200 철강/소재"), optional=True),
}


# ----------------------------------------------------------------------------
# 파싱 (HTTP 와 분리)
# ----------------------------------------------------------------------------

def parse_items(payload: Any) -> tuple[list[dict[str, Any]], int]:
    """data.go.kr 공통 JSON 봉투 → (item 목록, totalCount). 헤더 resultCode 가 00 이 아니면 오류."""
    if not isinstance(payload, dict):
        raise CollectorError(f"data.go.kr 응답 형식이 아님: {type(payload).__name__}")
    resp = payload.get("response", payload)
    header = resp.get("header", {}) or {}
    code = str(header.get("resultCode", "00"))
    if code not in ("00", "0"):
        raise CollectorError(f"data.go.kr 오류 {code}: {header.get('resultMsg', '')}")
    body = resp.get("body", {}) or {}
    total = int(body.get("totalCount", 0) or 0)
    items = body.get("items", "")
    if not items:
        return [], total
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return [i for i in items if isinstance(i, dict)], total


def parse_error_xml(text: str) -> str | None:
    """키 미등록 등 XML 오류 봉투에서 메시지를 뽑는다. XML 이 아니면 None."""
    s = text.lstrip()
    if not s.startswith("<"):
        return None
    try:
        root = ET.fromstring(s)
    except ET.ParseError:
        return s[:200]
    parts = [root.findtext(f".//{tag}") for tag in ("returnAuthMsg", "errMsg", "returnReasonCode", "resultMsg", "resultCode")]
    return " / ".join(p for p in parts if p) or s[:200]


def items_to_points(items: list[dict[str, Any]], *, expect_name: str | None = None, name_field: str = "idxNm",
                    price_field: str = "clpr") -> list[tuple[date, float]]:
    """item → (basDt, clpr). expect_name 이 있으면 이름(공백 무시)이 다른 행은 버린다 (부분 일치 방지)."""
    out: list[tuple[date, float]] = []
    want = _norm(expect_name) if expect_name else None
    for it in items:
        if want and _norm(it.get(name_field, "")) != want:
            continue
        d = base.parse_date(it.get("basDt"))
        v = base.to_float(it.get(price_field))
        if d is None or v is None:
            continue
        out.append((d, v))
    return out


def _norm(s: Any) -> str:
    return "".join(str(s or "").split()).upper()


def normalize_service_key(key: str) -> str:
    """공공데이터포털은 'Encoding/Decoding' 두 가지 키를 보여준다. httpx 가 다시 인코딩하므로 디코딩 키로 통일한다."""
    return unquote(key) if "%" in key else key


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------

def _get_items(client: httpx.Client, url: str, params: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    resp = base.get(client, url, params)
    err = parse_error_xml(resp.text)
    if err is not None:
        raise CollectorError(f"data.go.kr 오류 응답: {err}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise CollectorError(f"JSON 이 아닌 응답: {resp.text[:200]!r}") from exc
    return parse_items(payload)


def fetch_all(client: httpx.Client, service_key: str, spec: KrxSpec, rng: DateRange) -> list[dict[str, Any]]:
    """numOfRows/pageNo 로 전 페이지를 받아 item 목록을 돌려준다."""
    url = ENDPOINTS[spec.kind]
    params: dict[str, Any] = {
        "serviceKey": service_key, "resultType": "json", "numOfRows": PAGE_SIZE,
        "beginBasDt": base.yyyymmdd(rng.since), "endBasDt": base.yyyymmdd(rng.until),
    }
    if spec.kind == "index":
        params["idxNm"] = spec.match_name
    elif spec.code:
        params["likeSrtnCd"] = spec.code
    else:
        params["itmsNm"] = spec.match_name

    items: list[dict[str, Any]] = []
    page = 1
    while True:
        params["pageNo"] = page
        got, total = _get_items(client, url, params)
        items.extend(got)
        if not got or len(items) >= total or page * PAGE_SIZE >= total:
            break
        page += 1
    return items


def list_index_names(client: httpx.Client, service_key: str, rng: DateRange) -> list[str]:
    """최근 거래일 하루치의 모든 지수명 (idxNm 없이 조회). 업종지수 명칭 확인용."""
    url = ENDPOINTS["index"]
    params: dict[str, Any] = {"serviceKey": service_key, "resultType": "json", "numOfRows": 1000, "pageNo": 1,
                              "beginBasDt": base.yyyymmdd(rng.until - timedelta(days=10)), "endBasDt": base.yyyymmdd(rng.until)}
    try:
        got, _ = _get_items(client, url, params)
    except CollectorError as exc:
        log.warning("지수명 목록 조회 실패: %s", exc)
        return []
    return sorted({str(it.get("idxNm")) for it in got if it.get("idxNm")})


def run(session: Session, rng: DateRange, *, api_key: str | None = None,
        client: httpx.Client | None = None, only: list[str] | None = None) -> dict[str, Any]:
    key = api_key or settings.data_go_kr_api_key
    if not key:
        raise MissingApiKey("DATA_GO_KR_API_KEY 가 없습니다 (공공데이터포털에서 금융위원회 지수시세정보·증권상품시세정보 활용신청)")
    key = normalize_service_key(key)
    own = client is None
    client = client or base.make_client()
    counts: dict[str, Any] = {}
    try:
        for sid, spec in SERIES.items():
            if only and sid not in only:
                continue
            name = spec.name
            items = fetch_all(client, key, spec, rng)
            if spec.kind == "index":
                pts = items_to_points(items, expect_name=spec.match_name, name_field="idxNm")
                # 지수명이 바뀌었을 수 있으니 후보 이름을 차례로 시도한다
                for alt in spec.alt_names:
                    if pts:
                        break
                    alt_spec = replace(spec, match_name=alt)
                    items = fetch_all(client, key, alt_spec, rng)
                    pts = items_to_points(items, expect_name=alt, name_field="idxNm")
                    if pts:
                        log.info("%s: 지수명 '%s' 으로 수집 (%d건)", sid, alt, len(pts))
                        name = f"{spec.name} ({alt})"
                if not pts and spec.fallback:
                    # 끝내 못 찾으면 대리 시리즈로 저장하고, 포털이 돌려주는 지수명 목록을 기록한다
                    seen = list_index_names(client, key, rng)
                    counts[f"{sid}_names_seen"] = [n for n in seen if any(k in n for k in ("전기", "정보", "IT", "반도체", "기술"))][:20]
                    fb = SERIES[spec.fallback]
                    items = fetch_all(client, key, fb, rng)
                    pts = items_to_points(items, name_field="itmsNm")
                    name = f"{spec.name} 대리 — {fb.name}"
                    log.warning("%s: 업종지수를 찾지 못해 %s 를 대리로 저장 (%d건)", sid, spec.fallback, len(pts))
            else:
                pts = items_to_points(items, name_field="itmsNm")
                names = {it.get("itmsNm") for it in items}
                if len(names) > 1:
                    log.warning("%s: 한 코드에 여러 종목명이 섞임 %s — 매핑 표 확인", sid, sorted(map(str, names)))
            if items and not pts:
                log.warning("%s: %d건 받았지만 이름 '%s' 과 일치하는 행이 없음. 받은 이름 예: %s",
                            sid, len(items), spec.match_name,
                            sorted({str(it.get('idxNm') or it.get('itmsNm')) for it in items})[:8])
            if not pts and spec.optional:
                log.warning("%s (선택 시리즈): 받은 값이 없어 저장하지 않음", sid)
                counts[sid] = 0
                continue
            res = base.upsert_series(
                session, series_id=spec.series_id, name=name, source=SOURCE, unit=spec.unit, frequency="D",
                license=LICENSE, source_url=ENDPOINTS[spec.kind], points=pts)
            log.info("%s (%s %s): %s", sid, spec.kind, spec.code or spec.match_name, res.as_dict())
            counts[sid] = res.total
    finally:
        if own:
            client.close()
    return counts


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    base.add_range_args(ap)
    ap.add_argument("--only", help="쉼표로 구분한 series_id (예: KOSPI,US_EQ)")
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
