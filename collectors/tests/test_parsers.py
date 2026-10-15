"""응답 파서·upsert·CLI 로직 테스트 (네트워크 없음).

고정 응답(fixture)은 각 API 의 공개 문서 응답 형식을 작게 옮긴 것이다. 실제 응답과 다르면 해당 파서와 함께 고쳐야 한다.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import httpx
import pytest
from sqlalchemy import func, select

from app.models.tables import PolicyEvent, Series, SeriesValue
from collectors import base, ecos, federal_register, fred, korea_briefing, krx_prices, run_all
from collectors.base import CollectorError, DateRange

# ============================================================================
# base
# ============================================================================


@pytest.mark.parametrize("raw,expected", [
    ("3.95", 3.95), (".", None), ("", None), (None, None), ("1,300.4", 1300.4), ("-", None), ("nan", None),
    (2, 2.0), ("abc", None), ("NaN", None),
])
def test_to_float(raw, expected):
    assert base.to_float(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2024-01-02", date(2024, 1, 2)), ("20240102", date(2024, 1, 2)), ("2024.01.02", date(2024, 1, 2)),
    ("2024/01/02", date(2024, 1, 2)), ("2025-04-02 10:00:00.0", date(2025, 4, 2)),
    ("Wed, 02 Apr 2025 10:00:00 +0900", date(2025, 4, 2)), ("", None), (None, None), ("20241332", None),
    (datetime(2024, 1, 2, 5), date(2024, 1, 2)), (date(2024, 1, 2), date(2024, 1, 2)),
])
def test_parse_date(raw, expected):
    assert base.parse_date(raw) == expected


def test_resolve_range_defaults():
    r = base.resolve_range(None, "2024-12-31", default_since=date(2015, 1, 1))
    assert r == DateRange(date(2015, 1, 1), date(2024, 12, 31))
    r2 = base.resolve_range(None, "2024-12-31", default_days=30)
    assert r2.since == date(2024, 12, 1)
    with pytest.raises(ValueError):
        base.resolve_range("2025-01-01", "2024-01-01")


def _count(session, sid):
    return session.scalar(select(func.count()).select_from(SeriesValue).where(SeriesValue.series_id == sid))


def test_upsert_series_is_idempotent_and_updates(session):
    pts = [("2024-01-02", "3.95"), ("2024-01-03", 3.90), ("2024-01-04", "."), ("2024-01-03", 3.91)]
    r1 = base.upsert_series(session, "DGS10", "미국 국채 10년 금리", "FRED", "%", "D", "FRED terms", "https://x", pts)
    assert (r1.inserted, r1.updated, r1.skipped) == (2, 0, 2)  # "." 결측 1 + 중복 날짜 1
    assert r1.first == date(2024, 1, 2) and r1.last == date(2024, 1, 3)
    session.commit()
    assert _count(session, "DGS10") == 2
    v = session.scalar(select(SeriesValue.value).where(SeriesValue.series_id == "DGS10", SeriesValue.date == date(2024, 1, 3)))
    assert v == 3.91  # 같은 날짜는 마지막 값

    # 재실행: 행 수 그대로, 값·collected_at 갱신
    before = session.scalar(select(SeriesValue.collected_at).where(SeriesValue.series_id == "DGS10", SeriesValue.date == date(2024, 1, 2)))
    r2 = base.upsert_series(session, "DGS10", "미국 국채 10년 금리 (갱신)", "FRED", "%", "D", "FRED terms", "https://x",
                            [("2024-01-02", 4.00), ("2024-01-05", 4.01)])
    session.commit()
    assert (r2.inserted, r2.updated) == (1, 1)
    assert _count(session, "DGS10") == 3
    row = session.execute(select(SeriesValue.value, SeriesValue.collected_at)
                          .where(SeriesValue.series_id == "DGS10", SeriesValue.date == date(2024, 1, 2))).one()
    assert row.value == 4.00 and row.collected_at >= before
    assert session.get(Series, "DGS10").name == "미국 국채 10년 금리 (갱신)"


def test_upsert_series_replaces_synthetic(session):
    base.upsert_series(session, "WTI", "WTI (합성)", "SYNTHETIC", "USD/bbl", "D", "합성", "",
                       [(date(2015, 1, 2), 53.0), (date(2015, 1, 5), 52.0), (date(2024, 1, 2), 70.0)])
    session.commit()
    assert _count(session, "WTI") == 3
    r = base.upsert_series(session, "WTI", "WTI 유가", "FRED (Federal Reserve Bank of St. Louis)", "USD/bbl", "D",
                           "FRED terms", "https://fred", [(date(2024, 1, 2), 70.38)])
    session.commit()
    assert r.replaced_synthetic == 3 and r.inserted == 1
    assert _count(session, "WTI") == 1  # 2015년 합성 값이 남지 않는다
    assert session.get(Series, "WTI").source.startswith("FRED")
    # 실제 → 실제 재수집은 삭제하지 않는다
    r2 = base.upsert_series(session, "WTI", "WTI 유가", "FRED (Federal Reserve Bank of St. Louis)", "USD/bbl", "D",
                            "FRED terms", "https://fred", [(date(2024, 1, 3), 71.0)])
    assert r2.replaced_synthetic == 0 and _count(session, "WTI") == 2


def test_upsert_series_empty_points_only_writes_meta(session):
    r = base.upsert_series(session, "KTB3Y", "국고채 3년", "한국은행 ECOS", "%", "D", "lic", "", [])
    assert r.total == 0 and session.get(Series, "KTB3Y") is not None


def test_upsert_events_merges_and_clips(session):
    ev = {"event_id": "fr_2025-00001", "country": "US", "type": "tariff", "title": "T" * 400, "summary": "s",
          "targets": ["semiconductor"], "value": 25.0, "value_text": "25%", "announced_at": "2025-04-02",
          "source": "Federal Register", "source_url": "https://fr", "license": "PD", "raw_text": "r", "is_demo": False}
    assert base.upsert_events(session, [ev, {**ev, "title": "two"}]) == 2
    session.commit()
    stored = session.get(PolicyEvent, "fr_2025-00001")
    assert stored.title == "two" and len(stored.title) <= 300 and stored.announced_at == date(2025, 4, 2)
    assert session.scalar(select(func.count()).select_from(PolicyEvent)) == 1
    # announced_at 이 없으면 건너뜀
    assert base.upsert_events(session, [{"event_id": "x", "announced_at": None}]) == 0


def test_http_get_retries_then_succeeds(no_sleep):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json={"ok": True})

    with base.make_client(transport=httpx.MockTransport(handler)) as c:
        assert base.get_json(c, "https://example.test/x", {"a": 1}) == {"ok": True}
    assert calls["n"] == 3


def test_http_get_4xx_raises_immediately(no_sleep):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, text="bad")

    with base.make_client(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(CollectorError, match="HTTP 400"):
            base.get(c, "https://example.test/x")
    assert calls["n"] == 1


def test_http_get_5xx_exhausted_is_collector_error(no_sleep):
    with base.make_client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as c:
        with pytest.raises(CollectorError, match="HTTP 503"):
            base.get(c, "https://example.test/x", retries=1)


def test_http_get_gives_up_after_retries(no_sleep):
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with base.make_client(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(CollectorError):
            base.get(c, "https://example.test/x", retries=2)


# ============================================================================
# FRED
# ============================================================================

FRED_PAYLOAD = {
    "realtime_start": "2024-01-10", "realtime_end": "2024-01-10", "observation_start": "2024-01-01",
    "observation_end": "2024-01-05", "units": "lin", "output_type": 1, "file_type": "json", "order_by": "observation_date",
    "sort_order": "asc", "count": 4, "offset": 0, "limit": 100000,
    "observations": [
        {"realtime_start": "2024-01-10", "realtime_end": "2024-01-10", "date": "2024-01-01", "value": "."},
        {"realtime_start": "2024-01-10", "realtime_end": "2024-01-10", "date": "2024-01-02", "value": "3.95"},
        {"realtime_start": "2024-01-10", "realtime_end": "2024-01-10", "date": "2024-01-03", "value": "3.91"},
        {"realtime_start": "2024-01-10", "realtime_end": "2024-01-10", "date": "2024-01-04", "value": "3.99"},
    ],
}


def test_fred_parse_skips_dot_missing():
    pts = fred.parse_observations(FRED_PAYLOAD)
    assert pts == [(date(2024, 1, 2), 3.95), (date(2024, 1, 3), 3.91), (date(2024, 1, 4), 3.99)]


def test_fred_parse_error_payload():
    with pytest.raises(CollectorError, match="Bad Request"):
        fred.parse_observations({"error_code": 400, "error_message": "Bad Request. The value for variable api_key is not registered."})


def test_fred_series_table_has_no_third_party_indices():
    banned = {"SP500", "NASDAQCOM", "DJIA", "NASDAQ100", "WILL5000IND"}
    assert not banned & {s.fred_id for s in fred.SERIES.values()}
    assert fred.SERIES["DGS10"].unit == "%" and fred.SERIES["WTI"].fred_id == "DCOILWTICO"


def test_fred_run_end_to_end_with_mock_transport(session):
    seen: list[httpx.URL] = []

    def handler(request):
        seen.append(request.url)
        sid = request.url.params["series_id"]
        assert request.url.params["api_key"] == "k" and request.url.params["file_type"] == "json"
        assert request.url.params["observation_start"] == "2024-01-01"
        payload = dict(FRED_PAYLOAD)
        if sid == "DCOILWTICO":
            payload = {**FRED_PAYLOAD, "count": 1, "observations": [{"date": "2024-01-02", "value": "70.38"}]}
        return httpx.Response(200, json=payload)

    with base.make_client(transport=httpx.MockTransport(handler)) as c:
        counts = fred.run(session, DateRange(date(2024, 1, 1), date(2024, 1, 5)), api_key="k", client=c)
    session.commit()
    assert counts == {"DGS10": 3, "DGS2": 3, "DXY_BROAD": 3, "FED_TARGET_UPPER": 3, "WTI": 1}
    assert {u.params["series_id"] for u in seen} == {"DGS10", "DGS2", "DTWEXBGS", "DFEDTARU", "DCOILWTICO"}
    assert session.get(Series, "WTI").unit == "USD/bbl"
    assert "public domain" in session.get(Series, "DGS10").license


def test_fred_run_requires_key(session):
    with pytest.raises(base.MissingApiKey):
        fred.run(session, DateRange(date(2024, 1, 1), date(2024, 1, 5)), api_key=None)


# ============================================================================
# ECOS
# ============================================================================

ECOS_PAYLOAD = {"StatisticSearch": {"list_total_count": 3, "row": [
    {"STAT_CODE": "731Y001", "STAT_NAME": "1.3.2.1. 주요국 통화의 대원화 환율", "ITEM_CODE1": "0000001",
     "ITEM_NAME1": "원/미국달러(매매기준율)", "ITEM_CODE2": None, "ITEM_NAME2": None, "ITEM_CODE3": None, "ITEM_NAME3": None,
     "ITEM_CODE4": None, "ITEM_NAME4": None, "UNIT_NAME": "원", "WGT": None, "TIME": "20240102", "DATA_VALUE": "1300.4"},
    {"STAT_CODE": "731Y001", "ITEM_CODE1": "0000001", "UNIT_NAME": "원", "TIME": "20240103", "DATA_VALUE": "1304.8"},
    {"STAT_CODE": "731Y001", "ITEM_CODE1": "0000001", "UNIT_NAME": "원", "TIME": "20240104", "DATA_VALUE": ""},
]}}


def test_ecos_parse_rows_and_total():
    pts, total = ecos.parse_statistic_search(ECOS_PAYLOAD)
    assert total == 3
    assert pts == [(date(2024, 1, 2), 1300.4), (date(2024, 1, 3), 1304.8)]


def test_ecos_parse_no_data_and_errors():
    assert ecos.parse_statistic_search({"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}) == ([], 0)
    with pytest.raises(CollectorError, match="INFO-100"):
        ecos.parse_statistic_search({"RESULT": {"CODE": "INFO-100", "MESSAGE": "인증키가 유효하지 않습니다."}})
    with pytest.raises(CollectorError):
        ecos.parse_statistic_search({"Unexpected": {}})


def test_ecos_build_url_format():
    spec = ecos.SERIES["USDKRW"]
    url = ecos.build_url("KEY", spec, 1, 10000, DateRange(date(2015, 1, 1), date(2024, 12, 31)))
    assert url == "https://ecos.bok.or.kr/api/StatisticSearch/KEY/json/kr/1/10000/731Y001/D/20150101/20241231/0000001"


def test_ecos_run_pages_and_optional_series(session):
    """BOK_BASE_RATE(선택) 가 오류여도 필수 시리즈는 저장되고 전체는 성공한다."""
    def handler(request):
        path = request.url.path
        if "/722Y001/" in path:
            return httpx.Response(200, json={"RESULT": {"CODE": "INFO-100", "MESSAGE": "인증키 오류"}})
        if "/817Y002/" in path:
            return httpx.Response(200, json={"StatisticSearch": {"list_total_count": 1, "row": [
                {"TIME": "20240102", "DATA_VALUE": "3.25"}]}})
        return httpx.Response(200, json=ECOS_PAYLOAD)

    with base.make_client(transport=httpx.MockTransport(handler)) as c:
        counts = ecos.run(session, DateRange(date(2024, 1, 1), date(2024, 1, 5)), api_key="KEY", client=c)
    session.commit()
    assert counts == {"USDKRW": 2, "KTB3Y": 1, "BOK_BASE_RATE": 0, "KTB10Y": 1, "CORP3Y_AA": 1}
    assert session.get(Series, "USDKRW").source == "한국은행 ECOS"


# ============================================================================
# KRX (data.go.kr)
# ============================================================================

KRX_INDEX_PAYLOAD = {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."}, "body": {
    "numOfRows": 1000, "pageNo": 1, "totalCount": 3, "items": {"item": [
        {"basDt": "20240102", "idxNm": "코스피", "idxCsf": "KOSPI", "epyItmsCnt": "930", "clpr": "2669.81", "vs": "14.53",
         "fltRt": ".55", "mkp": "2645.47", "hipr": "2675.8", "lopr": "2641.69", "trqu": "406464476", "trPrc": "9136560000000",
         "lstgMrktTotAmt": "2126000000000000", "lsYrEdVsFltRg": "14.53", "lsYrEdVsFltRt": ".55", "yrWRcrdHgst": "2675.8",
         "yrWRcrdHgstDt": "20240102", "yrWRcrdLwst": "2641.69", "yrWRcrdLwstDt": "20240102", "basPntm": "19800104", "basIdx": "100"},
        {"basDt": "20240103", "idxNm": "코스피", "idxCsf": "KOSPI", "clpr": "2607.31"},
        {"basDt": "20240103", "idxNm": "코스피 200", "idxCsf": "KOSPI", "clpr": "351.22"},
    ]}}}}
KRX_ETF_PAYLOAD = {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."}, "body": {
    "numOfRows": 1000, "pageNo": 1, "totalCount": 1, "items": {"item":
        {"basDt": "20240102", "srtnCd": "360750", "isinCd": "KR7360750004", "itmsNm": "TIGER 미국S&P500", "clpr": "16250",
         "vs": "100", "fltRt": ".62", "nav": "16244.55", "mkp": "16150", "hipr": "16300", "lopr": "16120", "trqu": "1234567",
         "trPrc": "20000000000", "mrktTotAmt": "3000000000000", "nPptTotAmt": "3000000000000", "stLstgCnt": "185000000",
         "bssIdxIdxNm": "S&P 500", "bssIdxClpr": "4742.83"}}}}}
KRX_EMPTY_PAYLOAD = {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                                  "body": {"numOfRows": 1000, "pageNo": 1, "totalCount": 0, "items": ""}}}
DATA_GO_KR_ERROR_XML = """<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>
<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"""


def test_krx_parse_items_list_single_empty():
    items, total = krx_prices.parse_items(KRX_INDEX_PAYLOAD)
    assert total == 3 and len(items) == 3
    items, total = krx_prices.parse_items(KRX_ETF_PAYLOAD)
    assert total == 1 and items[0]["srtnCd"] == "360750"  # 단일 item 이 dict 로 와도 목록으로
    assert krx_prices.parse_items(KRX_EMPTY_PAYLOAD) == ([], 0)
    with pytest.raises(CollectorError, match="03"):
        krx_prices.parse_items({"response": {"header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"}, "body": {}}})


def test_krx_items_to_points_filters_exact_index_name():
    items, _ = krx_prices.parse_items(KRX_INDEX_PAYLOAD)
    assert krx_prices.items_to_points(items, expect_name="코스피") == [(date(2024, 1, 2), 2669.81), (date(2024, 1, 3), 2607.31)]
    assert krx_prices.items_to_points(items, expect_name="코스피 200") == [(date(2024, 1, 3), 351.22)]
    assert krx_prices.items_to_points(items, expect_name="코스피200") == [(date(2024, 1, 3), 351.22)]  # 공백 무시
    etf, _ = krx_prices.parse_items(KRX_ETF_PAYLOAD)
    assert krx_prices.items_to_points(etf, name_field="itmsNm") == [(date(2024, 1, 2), 16250.0)]


def test_krx_error_xml_and_service_key():
    assert "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in krx_prices.parse_error_xml(DATA_GO_KR_ERROR_XML)
    assert krx_prices.parse_error_xml(json.dumps(KRX_EMPTY_PAYLOAD)) is None
    assert krx_prices.normalize_service_key("abc%2Bdef%3D%3D") == "abc+def=="
    assert krx_prices.normalize_service_key("abc+def==") == "abc+def=="


def test_krx_mapping_table_covers_catalog_and_portfolio_series():
    from app.engine.catalog import FACTOR_IDS

    needed = {"KOSPI", "KOSPI_IT", "US_EQ"} | {"KR_SEMI", "KR_K200", "KR_AUTO", "US_TECH"}
    assert needed <= set(krx_prices.SERIES)
    assert {"KOSPI", "KOSPI_IT", "US_EQ"} <= set(FACTOR_IDS)
    for sid, spec in krx_prices.SERIES.items():
        assert spec.kind in krx_prices.ENDPOINTS
        assert spec.kind == "index" or spec.code, f"{sid}: ETF 는 단축코드가 필요"


def test_krx_run_pages_and_handles_xml_error(session):
    """2 페이지 응답과 키 오류 XML 을 함께 검증한다."""
    page1 = {"response": {"header": {"resultCode": "00"}, "body": {"totalCount": 2, "numOfRows": 1, "pageNo": 1, "items": {"item": [
        {"basDt": "20240102", "idxNm": "코스피", "clpr": "2669.81"}]}}}}
    page2 = {"response": {"header": {"resultCode": "00"}, "body": {"totalCount": 2, "numOfRows": 1, "pageNo": 2, "items": {"item": [
        {"basDt": "20240103", "idxNm": "코스피", "clpr": "2607.31"}]}}}}

    def handler(request):
        assert request.url.params["serviceKey"] == "dec+key=="
        if "getStockMarketIndex" in request.url.path and request.url.params.get("idxNm") == "코스피":
            return httpx.Response(200, json=page1 if request.url.params["pageNo"] == "1" else page2)
        if "getETFPriceInfo" in request.url.path:
            assert request.url.params["likeSrtnCd"] == "360750"
            return httpx.Response(200, json=KRX_ETF_PAYLOAD)
        return httpx.Response(200, json=KRX_EMPTY_PAYLOAD)

    original = krx_prices.PAGE_SIZE
    krx_prices.PAGE_SIZE = 1
    try:
        with base.make_client(transport=httpx.MockTransport(handler)) as c:
            counts = krx_prices.run(session, DateRange(date(2024, 1, 1), date(2024, 1, 5)), api_key="dec%2Bkey%3D%3D",
                                    client=c, only=["KOSPI", "US_EQ", "KR_K200"])
    finally:
        krx_prices.PAGE_SIZE = original
    session.commit()
    assert counts == {"KOSPI": 2, "US_EQ": 1, "KR_K200": 0}
    assert session.get(Series, "US_EQ").unit == "KRW"

    def bad(request):
        return httpx.Response(200, text=DATA_GO_KR_ERROR_XML)

    with base.make_client(transport=httpx.MockTransport(bad)) as c:
        with pytest.raises(CollectorError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
            krx_prices.run(session, DateRange(date(2024, 1, 1), date(2024, 1, 5)), api_key="k", client=c, only=["KOSPI"])


# ============================================================================
# Federal Register
# ============================================================================

FR_PAYLOAD = {
    "count": 2, "description": "Documents matching 'tariff'", "total_pages": 1, "next_page_url": None,
    "results": [
        {"document_number": "2025-05930", "title": "Regulating Imports With a Reciprocal Tariff To Rectify Trade Practices",
         "abstract": "Imposes an additional ad valorem duty of 10 percent on all imports from all trading partners, with higher "
                     "rates for certain countries. Semiconductors are excluded.",
         "type": "Presidential Document", "subtype": "Executive Order", "publication_date": "2025-04-07",
         "html_url": "https://www.federalregister.gov/documents/2025/04/07/2025-05930/x",
         "body_html_url": "https://www.federalregister.gov/documents/full_text/html/2025/04/07/2025-05930.html",
         "agencies": [{"raw_name": "Executive Office of the President", "name": "Executive Office of the President",
                       "id": 168, "url": "https://www.federalregister.gov/agencies/executive-office-of-the-president",
                       "json_url": "https://www.federalregister.gov/api/v1/agencies/168", "parent_id": None,
                       "slug": "executive-office-of-the-president"}]},
        {"document_number": "2025-01234", "title": "Export Controls on Advanced Computing Items",
         "abstract": "This rule revises license requirements for advanced computing integrated circuits.",
         "type": "Rule", "publication_date": "2025-01-15",
         "html_url": "https://www.federalregister.gov/documents/2025/01/15/2025-01234/y", "body_html_url": None,
         "agencies": [{"name": "Commerce Department", "slug": "commerce-department"},
                      {"name": "Industry and Security Bureau", "slug": "industry-and-security-bureau"}]},
        {"document_number": None, "title": "broken", "publication_date": "2025-01-01"},
    ],
}


def test_fr_parse_documents():
    results, count, nxt = federal_register.parse_documents(FR_PAYLOAD)
    assert count == 2 and nxt is None and len(results) == 3
    with pytest.raises(CollectorError):
        federal_register.parse_documents({"errors": {"term": ["is invalid"]}})


def test_fr_document_to_event_tariff_with_percent():
    ev = federal_register.document_to_event(FR_PAYLOAD["results"][0])
    assert ev["event_id"] == "fr_2025-05930" and ev["country"] == "US" and ev["type"] == "tariff"
    assert ev["value"] == 10.0 and ev["value_text"] == "10%"
    assert ev["announced_at"] == date(2025, 4, 7) and ev["is_demo"] is False
    assert ev["source"] == "Federal Register" and ev["source_url"].endswith("2025-05930/x")
    assert "로고" in ev["license"] and "Public domain" in ev["license"]
    assert "본문: https://www.federalregister.gov/documents/full_text" in ev["raw_text"]
    assert "all_imports" in ev["targets"] and "semiconductor" in ev["targets"]


def test_fr_document_to_event_regulation_without_percent():
    ev = federal_register.document_to_event(FR_PAYLOAD["results"][1])
    assert ev["type"] == "regulation" and ev["value"] is None and ev["value_text"] == ""
    assert ev["targets"] == ["semiconductor"]
    assert "기관: Commerce Department, Industry and Security Bureau" in ev["raw_text"]
    assert federal_register.document_to_event(FR_PAYLOAD["results"][2]) is None


@pytest.mark.parametrize("text,expected", [
    ("a 25 percent tariff", (25.0, "25%")), ("duty of 7.5%", (7.5, "7.5%")), ("raise by 0.25 percentage points", (0.25, "0.25%p")),
    ("no number here", (None, "")),
])
def test_fr_extract_percent(text, expected):
    assert federal_register.extract_percent(text) == expected


def test_fr_build_params_repeats_array_keys():
    params = federal_register.build_params("tariff", DateRange(date(2025, 1, 1), date(2025, 6, 30)), page=2)
    keys = [k for k, _ in params]
    assert keys.count("conditions[agencies][]") == len(federal_register.AGENCIES)
    assert keys.count("conditions[type][]") == 2 and ("page", 2) in params
    assert ("conditions[publication_date][gte]", "2025-01-01") in params


@pytest.mark.parametrize("title,abstract,doc_type,etype,targets,expected", [
    ("Adjusting Imports of Semiconductors Into the United States", "25 percent ad valorem tariff", "Presidential Document", "tariff",
     ["semiconductor"], "high"),
    ("Regulating Imports With a Reciprocal Tariff", "all trading partners", "Presidential Document", "tariff", ["all_imports"], "high"),
    ("Certain Pasta From Italy: Final Results of Antidumping Duty Administrative Review", "", "Notice", "tariff", [], "low"),
    ("Additions to the Entity List; Revisions to Export Controls on Advanced Computing", "semiconductor manufacturing", "Rule",
     "regulation", ["semiconductor"], "high"),
    ("Honey From Argentina: Preliminary Determination", "antidumping", "Notice", "tariff", [], "low"),
    ("Modification of Section 301 Action: China's Acts", "tariff increases", "Notice", "tariff", [], "high"),
    ("Procedures for Submitting Requests", "", "Rule", "regulation", [], "low"),
])
def test_fr_score_relevance(title, abstract, doc_type, etype, targets, expected):
    assert federal_register.score_relevance(title, abstract, doc_type, etype, targets) == expected


def test_upsert_events_preserves_localized_fields(session):
    """한국어화된 이벤트(title_orig 있음)는 재수집해도 LLM 이 채운 제목·요약·관련성을 지키고 원문·수집 시각만 갱신한다."""
    ev = {"event_id": "fr_LOC1", "country": "US", "type": "regulation", "title": "English title", "summary": "en",
          "announced_at": "2025-03-01", "source": "Federal Register", "raw_text": "v1", "relevance": "mid"}
    base.upsert_events(session, [ev])
    session.flush()
    row = session.get(PolicyEvent, "fr_LOC1")
    assert row.relevance == "mid"
    row.title_orig, row.title, row.summary, row.type, row.relevance = row.title, "한국어 제목", "한국어 요약", "tariff", "high"
    session.flush()
    base.upsert_events(session, [{**ev, "raw_text": "v2", "title": "English title (corrected)"}])
    session.flush()
    row = session.get(PolicyEvent, "fr_LOC1")
    assert (row.title, row.summary, row.type, row.relevance, row.raw_text) == ("한국어 제목", "한국어 요약", "tariff", "high", "v2")


def test_fr_run_dedupes_across_terms(session):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=FR_PAYLOAD)  # 모든 검색어에 같은 문서 → 중복 제거 확인

    with base.make_client(transport=httpx.MockTransport(handler)) as c:
        counts = federal_register.run(session, DateRange(date(2025, 1, 1), date(2025, 6, 30)), client=c)
    session.commit()
    assert calls["n"] == len(federal_register.SEARCH_TERMS)
    assert counts == {"documents": 2, "events": 2, "tariff": 1, "regulation": 1,
                      "relevance_high": 2, "relevance_mid": 0, "relevance_low": 0}
    assert session.scalar(select(func.count()).select_from(PolicyEvent)) == 2
    assert {e.relevance for e in session.scalars(select(PolicyEvent))} == {"high"}
    # 재실행해도 늘지 않는다
    with base.make_client(transport=httpx.MockTransport(handler)) as c:
        federal_register.run(session, DateRange(date(2025, 1, 1), date(2025, 6, 30)), client=c)
    session.commit()
    assert session.scalar(select(func.count()).select_from(PolicyEvent)) == 2


# ============================================================================
# 대한민국 정책브리핑
# ============================================================================

KR_API_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>0</resultCode><resultMsg>success</resultMsg></header>
  <body>
    <totalCount>3</totalCount>
    <NewsItem>
      <NewsItemId>148930001</NewsItemId><ContentsStatus>U</ContentsStatus>
      <ApproveDate>2025-04-03 09:30:00.0</ApproveDate>
      <Title>미국 상호관세 발표 관련 긴급 경제장관회의 개최</Title>
      <SubTitle1>반도체·자동차 등 주력 품목 영향 점검, 25% 관세 대응방안 논의</SubTitle1>
      <DataContents><![CDATA[<p>정부는 미국의 상호관세 발표에 따라 반도체, 자동차 업종 영향을 점검했다.</p>
        <p class="copyright">본 저작물은 공공누리 제1유형 조건에 따라 이용할 수 있습니다.</p>]]></DataContents>
      <MinisterCode>기획재정부</MinisterCode>
      <OriginalUrl>https://www.korea.kr/briefing/pressReleaseView.do?newsId=156680001</OriginalUrl>
    </NewsItem>
    <NewsItem>
      <NewsItemId>148930002</NewsItemId>
      <ApproveDate>2025-04-03 11:00:00.0</ApproveDate>
      <Title>통화정책방향: 기준금리 0.25%p 인하</Title>
      <SubTitle1></SubTitle1>
      <DataContents><![CDATA[<p>금융통화위원회는 기준금리를 연 2.75%에서 2.50%로 0.25%p 인하하기로 의결했다.</p>]]></DataContents>
      <MinisterCode>한국은행</MinisterCode>
      <OriginalUrl>https://www.korea.kr/briefing/pressReleaseView.do?newsId=156680002</OriginalUrl>
    </NewsItem>
    <NewsItem>
      <NewsItemId>148930003</NewsItemId>
      <ApproveDate>2025-04-03 12:00:00.0</ApproveDate>
      <Title>봄철 산불 예방 캠페인</Title>
      <DataContents><![CDATA[<p>산림청은 … 공공누리 제4유형</p>]]></DataContents>
      <MinisterCode>산림청</MinisterCode>
      <OriginalUrl>https://www.korea.kr/briefing/pressReleaseView.do?newsId=156680003</OriginalUrl>
    </NewsItem>
  </body>
</response>"""

KR_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>정책브리핑 보도자료</title>
<item>
  <title>[산업통상자원부] 미 반도체 수출통제 강화에 따른 업계 간담회</title>
  <link>https://www.korea.kr/briefing/pressReleaseView.do?newsId=156680101</link>
  <description><![CDATA[산업통상자원부는 미국의 반도체 수출통제 조치와 관련해 … ]]></description>
  <pubDate>Thu, 03 Apr 2025 14:00:00 +0900</pubDate>
  <author>산업통상자원부</author>
</item>
<item>
  <title>금융위원회, 가상자산 규제 개선 방안 발표</title>
  <link>https://www.korea.kr/briefing/pressReleaseView.do?newsId=156680102</link>
  <description>금융위원회는 … 규제 개선</description>
  <pubDate>Thu, 03 Apr 2025 15:00:00 +0900</pubDate>
  <dc:creator>금융위원회</dc:creator>
</item>
</channel></rss>"""


def test_kr_parse_api_xml():
    items, total = korea_briefing.parse_press_release_xml(KR_API_XML)
    assert total == 3 and len(items) == 3
    first = items[0]
    assert first["ministry"] == "기획재정부" and first["date"] == date(2025, 4, 3)
    assert first["title"].startswith("미국 상호관세") and "<p>" not in first["body"]
    assert first["url"].endswith("156680001")
    with pytest.raises(CollectorError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
        korea_briefing.parse_press_release_xml(DATA_GO_KR_ERROR_XML)
    with pytest.raises(CollectorError):
        korea_briefing.parse_press_release_xml("not xml at all")


def test_kr_parse_rss():
    items = korea_briefing.parse_rss(KR_RSS)
    assert len(items) == 2
    assert items[0]["ministry"] == "산업통상자원부" and items[0]["date"] == date(2025, 4, 3)
    assert items[1]["ministry"] == "금융위원회"  # dc:creator 폴백
    assert items[0]["url"].endswith("156680101")


@pytest.mark.parametrize("text,expected", [
    ("본 저작물은 공공누리 제1유형 조건에 따라", korea_briefing.KOGL_LABELS["1"]),
    ("공공누리 4유형", korea_briefing.KOGL_LABELS["4"]),
    ("KOGL Type 2", korea_briefing.KOGL_LABELS["2"]),
    ("저작권 표시 없음", None), ("", None), (None, None),
])
def test_kr_detect_kogl(text, expected):
    assert korea_briefing.detect_kogl(text) == expected


def test_kr_select_and_convert_filters_and_types():
    items, _ = korea_briefing.parse_press_release_xml(KR_API_XML)
    events, skipped = korea_briefing.select_and_convert(items)
    # 1) 기재부·관세·공공누리1유형 → tariff 저장, 2) 한국은행·기준금리 but 공공누리 없음 → 건너뜀, 3) 산림청 → 부처 불일치
    assert len(events) == 1
    ev = events[0]
    assert ev["type"] == "tariff" and ev["country"] == "KR" and ev["event_id"].startswith("kr_") and len(ev["event_id"]) == 19
    assert ev["license"].startswith("공공누리 제1유형") and "기획재정부" in ev["license"]
    assert ev["value"] == 25.0 and ev["value_text"] == "25%"
    assert set(ev["targets"]) >= {"semiconductor", "automobile", "all_imports"}
    assert ev["summary"].startswith("반도체·자동차")
    assert skipped["skipped_no_license"] == 1 and skipped["skipped_no_ministry"] == 1

    # 공공누리가 기사 페이지 텍스트(page_text)에서 식별되면 저장된다 (RSS 폴백 경로)
    items[1]["page_text"] = "… 공공누리 제1유형 …"
    events2, _ = korea_briefing.select_and_convert(items)
    assert [e["type"] for e in events2] == ["tariff", "rate"]
    assert events2[1]["value_text"] == "0.25%p"


def test_kr_event_id_is_stable():
    a = korea_briefing.make_event_id("https://x/1", "t", date(2025, 1, 1))
    assert a == korea_briefing.make_event_id("https://x/1", "other", date(2024, 1, 1))  # URL 우선
    assert a != korea_briefing.make_event_id("", "t", date(2025, 1, 1))


def test_kr_run_rss_fallback_fetches_pages_for_license(session):
    def handler(request):
        if request.url.path.endswith("pressrelease.xml"):
            return httpx.Response(200, text=KR_RSS)
        if "156680101" in str(request.url):
            return httpx.Response(200, text="<html><body>본문 … <img alt='공공누리 제1유형'> 공공누리 제1유형 : 출처표시</body></html>")
        return httpx.Response(200, text="<html><body>저작권 표시 없음</body></html>")

    with base.make_client(transport=httpx.MockTransport(handler)) as c:
        counts = korea_briefing.run(session, DateRange(date(2025, 1, 1), date(2025, 12, 31)), api_key=None, client=c)
    session.commit()
    assert counts["mode"] == "RSS" and counts["items"] == 2 and counts["events"] == 1
    assert counts["skipped_no_license"] == 1
    ev = session.scalars(select(PolicyEvent)).one()
    assert ev.type == "regulation" and ev.license.startswith("공공누리 제1유형") and ev.targets == ["semiconductor"]


def test_kr_run_api_mode(session):
    seen_starts: list[str] = []

    def handler(request):
        assert request.url.params["serviceKey"] == "k"
        seen_starts.append(request.url.params["startDate"])
        return httpx.Response(200, text=KR_API_XML)

    with base.make_client(transport=httpx.MockTransport(handler)) as c:
        counts = korea_briefing.run(session, DateRange(date(2025, 4, 1), date(2025, 4, 7)), api_key="k", client=c)
    assert seen_starts == ["20250405", "20250402", "20250401"]  # 3일 창, 최신부터
    assert counts["mode"] == "data.go.kr API" and counts["events"] == 1


# ============================================================================
# run_all
# ============================================================================

class _Settings:
    fred_api_key = None
    ecos_api_key = "e"
    data_go_kr_api_key = None


def test_run_all_skips_missing_keys_and_isolates_errors(engine):
    from sqlalchemy.orm import sessionmaker
    from contextlib import contextmanager

    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @contextmanager
    def scope():
        s = Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    fred_c = next(c for c in run_all.REGISTRY if c.name == "fred")
    rep = run_all.run_one(fred_c, scope, None, None, _Settings())
    assert rep.status == "skipped" and "FRED_API_KEY" in rep.message

    boom = run_all.Collector("boom", lambda s, r: 1 / 0, None, date(2024, 1, 1), "")
    rep = run_all.run_one(boom, scope, None, None, _Settings())
    assert rep.status == "error" and rep.counts.get("unexpected") is True

    api_err = run_all.Collector("apierr", lambda s, r: (_ for _ in ()).throw(CollectorError("bad key")), None, date(2024, 1, 1), "")
    rep = run_all.run_one(api_err, scope, None, None, _Settings())
    assert rep.status == "error" and "bad key" in rep.message and "unexpected" not in rep.counts

    ok = run_all.Collector("ok", lambda s, r: {"X": 3}, "ecos_api_key", date(2024, 1, 1), "")
    rep = run_all.run_one(ok, scope, date(2024, 2, 1), date(2024, 2, 2), _Settings())
    assert rep.status == "ok" and rep.counts == {"X": 3} and "2024-02-01~2024-02-02" in rep.line()


def test_run_all_parse_only():
    assert run_all.parse_only(None) == run_all.NAMES
    assert run_all.parse_only("fred, ecos") == ["fred", "ecos"]
    with pytest.raises(SystemExit):
        run_all.parse_only("nope")


def test_run_all_exit_codes(monkeypatch, engine):
    """API 오류 → 0 (--strict 면 1), 예상치 못한 예외 → 1, 키 없음 → 0."""
    from app import db

    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(bind=engine, future=True))
    api_err = run_all.Collector("apierr", lambda s, r: (_ for _ in ()).throw(CollectorError("bad key")), None, date(2024, 1, 1), "")
    bug = run_all.Collector("bug", lambda s, r: 1 / 0, None, date(2024, 1, 1), "")
    nokey = run_all.Collector("nokey", lambda s, r: {"X": 1}, "fred_api_key", date(2024, 1, 1), "")

    monkeypatch.setattr(run_all, "REGISTRY", [api_err, nokey])
    monkeypatch.setattr(run_all, "NAMES", ["apierr", "nokey"])
    assert run_all.main([]) == 0
    assert run_all.main(["--strict"]) == 1
    monkeypatch.setattr(run_all, "REGISTRY", [bug, nokey])
    monkeypatch.setattr(run_all, "NAMES", ["bug", "nokey"])
    assert run_all.main(["--only", "nokey"]) == 0
    assert run_all.main([]) == 1


def test_run_all_list_runs_without_network(capsys):
    assert run_all.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "fred" in out and "FRED_API_KEY" in out and "federal_register" in out


def test_parse_date_accepts_14_digit_timestamp():
    assert base.parse_date("20261014103000") == date(2026, 10, 14)
    assert base.parse_date("20261014") == date(2026, 10, 14)
    assert base.parse_date("2026-10-14 10:30:00.0") == date(2026, 10, 14)
    assert base.parse_date("2026101") is None


def test_kr_parse_falls_back_to_any_date_like_tag_and_reports_tags():
    xml = """<response><header><resultCode>0</resultCode></header><body><totalCount>1</totalCount>
      <NewsItem><NewsItemId>1</NewsItemId><Title>관세 대응 점검</Title><MinisterCode>기획재정부</MinisterCode>
      <RegDt>20261014103000</RegDt><OriginalUrl>https://x/1</OriginalUrl><DataContents>공공누리 제1유형</DataContents></NewsItem>
    </body></response>"""
    items, total = korea_briefing.parse_press_release_xml(xml)
    assert total == 1 and items[0]["date"] == date(2026, 10, 14)
    assert "RegDt" in items[0]["_tags"] and "Title" in items[0]["_tags"]


def test_kr_windows_split_three_days_inclusive():
    w = korea_briefing.windows(date(2025, 4, 1), date(2025, 4, 8))
    assert w == [(date(2025, 4, 6), date(2025, 4, 8)), (date(2025, 4, 3), date(2025, 4, 5)), (date(2025, 4, 1), date(2025, 4, 2))]
    assert korea_briefing.windows(date(2025, 4, 8), date(2025, 4, 8)) == [(date(2025, 4, 8), date(2025, 4, 8))]


def test_kr_fetch_api_uses_three_day_windows_and_dedupes(session):
    calls: list[tuple[str, str, str]] = []

    def handler(request):
        p = request.url.params
        calls.append((request.url.path, p["startDate"], p["endDate"]))
        return httpx.Response(200, text=KR_API_XML)  # 모든 창에 같은 항목 → 중복 제거 확인

    with base.make_client(transport=httpx.MockTransport(handler)) as c:
        items = korea_briefing.fetch_api(c, "KEY", DateRange(date(2025, 4, 1), date(2025, 4, 7)))
    assert [(s, e) for _, s, e in calls] == [("20250405", "20250407"), ("20250402", "20250404"), ("20250401", "20250401")]
    assert all(path.endswith("/policyNewsService2/policyNewsList2") for path, _, _ in calls)
    assert len(items) == len(korea_briefing.parse_press_release_xml(KR_API_XML)[0])


def test_redact_hides_service_key_in_errors():
    assert base.redact("HTTP 400 from https://x/y?serviceKey=abc%2Fdef&pageNo=1") == "HTTP 400 from https://x/y?serviceKey=***&pageNo=1"
    assert base.redact("api_key=SECRET&file_type=json") == "api_key=***&file_type=json"
