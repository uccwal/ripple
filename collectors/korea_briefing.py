"""대한민국 정책브리핑(korea.kr) 보도자료 수집기 — 관세·수출통제·기준금리·규제 관련 자료를 PolicyEvent 로 저장.

    PYTHONPATH=backend:. python -m collectors.korea_briefing --since 2025-01-01

데이터 경로 (둘 중 하나)
1) 공공데이터포털 「문화체육관광부_대한민국 정책브리핑 보도자료」 API (DATA_GO_KR_API_KEY 가 있을 때)
     https://apis.data.go.kr/1371000/pressReleaseService/pressReleaseList?serviceKey=…&startDate=YYYYMMDD&endDate=YYYYMMDD&pageNo=…&numOfRows=…
     응답(XML): <response><header><resultCode>0</resultCode>…</header><body><NewsItem><NewsItemId/><Title/><SubTitle1/>
                <ApproveDate>2025-04-02 10:00:00.0</ApproveDate><MinisterCode>기획재정부</MinisterCode><DataContents><![CDATA[…]]></DataContents>
                <OriginalUrl>https://www.korea.kr/briefing/pressReleaseView.do?newsId=…</OriginalUrl></NewsItem>…</body></response>
     ※ 태그 이름은 공개 문서 기준이며 이 샌드박스에서 실제 응답으로 확인하지 못했다. 파서는 대소문자·별칭을 느슨하게 받는다.
2) korea.kr RSS (키 없을 때 폴백): https://www.korea.kr/rss/pressrelease.xml — 최근 자료만 제공된다.
     RSS 본문에는 공공누리 표시가 없는 경우가 많아, 기사 페이지를 추가로 받아 공공누리 유형을 찾는다 (fetch_pages=True, 상한 MAX_PAGE_FETCH).

적재 규칙 (docs/DESIGN.md 4장: "공공누리 유형이 표시된 자료만 수집, 유형별 출처 표시")
- 부처 필터: MINISTRIES 중 하나가 부처 필드·제목·본문에 있어야 한다.
- 키워드 필터: KEYWORDS 중 하나가 제목·본문에 있어야 한다. type 은 키워드로 정한다 (관세→tariff, 기준금리→rate, 그 밖→regulation).
- 공공누리 유형(제1~4유형)이 필드 또는 본문 텍스트("공공누리 제1유형" 등)에서 식별되는 자료만 저장하고, license 에 그 유형을 적는다.
  식별되지 않으면 건너뛰고 skipped_no_license 로 센다.
- event_id="kr_"+sha1(원문 URL 또는 제목+날짜)[:16], country="KR", is_demo=False, source="대한민국 정책브리핑 (korea.kr)".

주의: 네트워크가 차단된 환경에서 작성되어 실제 호출을 검증하지 못했다. 먼저 `--only korea_briefing` 으로 스모크 테스트할 것.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings

from . import base
from .base import MissingApiKey, CollectorError, DateRange

log = logging.getLogger("collectors.korea_briefing")

REQUIRED_KEY = None  # 키가 있으면 공공데이터포털 API, 없으면 RSS 폴백 (건너뛰지 않음)
DEFAULT_DAYS = 365
API_URL = "https://apis.data.go.kr/1371000/pressReleaseService/pressReleaseList"
# 포털의 '문화체육관광부_정책브리핑_정책뉴스_API'(데이터 15095335)는 policyNewsList2 오퍼레이션을 제공한다.
# 키는 활용신청한 서비스에만 등록되므로 후보를 차례로 시도하고 처음 성공한 주소를 쓴다.
API_CANDIDATES = [
    "https://apis.data.go.kr/1371000/policyNewsService/policyNewsList2",
    "https://apis.data.go.kr/1371000/policyNewsService/policyNewsList",
    API_URL,
]
RSS_URL = "https://www.korea.kr/rss/pressrelease.xml"
# korea.kr RSS 주소는 개편으로 바뀔 수 있어 후보를 차례로 시도한다 (첫 성공 사용). 전부 실패하면 '건너뜀'으로 보고.
RSS_CANDIDATES = [RSS_URL, "https://www.korea.kr/rss/policy.xml", "https://www.korea.kr/rss/news.xml",
                  "https://www.korea.kr/rss/briefing.xml"]
SOURCE = "대한민국 정책브리핑 (korea.kr)"
PAGE_SIZE = 100
MAX_PAGES = 50
MAX_PAGE_FETCH = 40  # RSS 폴백에서 공공누리 확인을 위해 받아 보는 기사 페이지 상한

# 부처 목록 (편집 가능). 2025~26년 정부조직 개편으로 명칭이 바뀐 부처는 신·구 명칭을 함께 둔다.
MINISTRIES: list[str] = [
    "기획재정부", "재정경제부", "기획예산처",  # 기재부 → 재경부·기획예산처 분리
    "산업통상자원부", "산업통상부",  # 산업부 명칭 변경
    "금융위원회", "한국은행", "관세청", "통상교섭본부",
]
# 키워드 → 이벤트 유형. 앞에서부터 먼저 맞는 유형을 쓴다.
KEYWORD_TYPES: list[tuple[str, str]] = [
    ("관세", "tariff"), ("상호관세", "tariff"), ("통상협상", "tariff"),
    ("기준금리", "rate"), ("금융통화위원회", "rate"), ("금통위", "rate"),
    ("수출통제", "regulation"), ("수출규제", "regulation"), ("규제", "regulation"), ("제재", "regulation"),
]
KEYWORDS: list[str] = [k for k, _ in KEYWORD_TYPES]
TARGET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "semiconductor": ("반도체",), "display": ("디스플레이",), "automobile": ("자동차",), "steel": ("철강",),
    "battery": ("배터리", "이차전지"), "policy_rate": ("기준금리",), "agriculture": ("농산물", "쌀", "소고기"),
    "all_imports": ("상호관세", "전 품목"),
}
_KOGL_RE = re.compile(r"공공누리\s*(?:\(KOGL\)\s*)?(?:제)?\s*([1-4])\s*유형")
_KOGL_TYPE_RE = re.compile(r"(?:KOGL|공공누리)[^0-9]{0,20}(?:TYPE|type|제)?\s*([1-4])")
KOGL_LABELS = {
    "1": "공공누리 제1유형 (출처표시)",
    "2": "공공누리 제2유형 (출처표시 + 상업적 이용금지)",
    "3": "공공누리 제3유형 (출처표시 + 변경금지)",
    "4": "공공누리 제4유형 (출처표시 + 상업적 이용금지 + 변경금지)",
}
_PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(%p|포인트|bp|%|퍼센트)")  # %p 를 % 보다 먼저
_TAG_RE = re.compile(r"<[^>]+>")


# ----------------------------------------------------------------------------
# 텍스트 도우미
# ----------------------------------------------------------------------------

def strip_html(s: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", s or ""))).strip()


def detect_kogl(*texts: str | None) -> str | None:
    """텍스트에서 공공누리 유형(1~4)을 찾아 라벨을 돌려준다. 없으면 None."""
    for t in texts:
        if not t:
            continue
        m = _KOGL_RE.search(t) or _KOGL_TYPE_RE.search(t)
        if m:
            return KOGL_LABELS[m.group(1)]
    return None


def classify(text: str) -> str | None:
    for kw, typ in KEYWORD_TYPES:
        if kw in text:
            return typ
    return None


def match_ministry(*texts: str | None) -> str | None:
    for t in texts:
        if not t:
            continue
        for m in MINISTRIES:
            if m in t:
                return m
    return None


def extract_targets(text: str) -> list[str]:
    return [tgt for tgt, kws in TARGET_KEYWORDS.items() if any(k in text for k in kws)]


def extract_value(text: str) -> tuple[float | None, str]:
    m = _PERCENT_RE.search(text or "")
    if not m:
        return None, ""
    v = base.to_float(m.group(1))
    if v is None:
        return None, ""
    unit = m.group(2)
    if unit in ("%p", "포인트"):
        return v, f"{v:g}%p"
    if unit == "bp":
        return v / 100, f"{v:g}bp"
    return v, f"{v:g}%"


def make_event_id(url: str | None, title: str, d: date | None) -> str:
    key = (url or "").strip() or f"{title.strip()}|{d}"
    return "kr_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------------------------
# 파싱 (HTTP 와 분리)
# ----------------------------------------------------------------------------

def _child_text(node: ET.Element, *names: str) -> str:
    """태그 이름을 대소문자 구분 없이 찾는다 (NewsItemId / newsItemId 등)."""
    wanted = {n.lower() for n in names}
    for child in node.iter():
        tag = child.tag.split("}")[-1].lower()
        if tag in wanted and child is not node:
            return (child.text or "").strip()
    return ""


def parse_press_release_xml(text: str) -> tuple[list[dict[str, Any]], int]:
    """공공데이터포털 보도자료 API(XML) → (items, totalCount). 각 item: title, body, ministry, url, date, license."""
    try:
        root = ET.fromstring(text.lstrip())
    except ET.ParseError as exc:
        raise CollectorError(f"보도자료 API 응답 XML 파싱 실패: {text[:200]!r}") from exc
    if root.tag == "OpenAPI_ServiceResponse":  # 키 오류 봉투
        raise CollectorError("data.go.kr 오류 응답: " + (root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg") or ""))
    code = (root.findtext(".//resultCode") or "0").strip()
    if code not in ("0", "00", "INFO-0", "NORMAL_CODE"):
        raise CollectorError(f"보도자료 API 오류 {code}: {root.findtext('.//resultMsg') or ''}")
    total = base.to_float(root.findtext(".//totalCount") or "0") or 0
    items: list[dict[str, Any]] = []
    for node in root.iter():
        if node.tag.split("}")[-1].lower() not in ("newsitem", "item"):
            continue
        title = _child_text(node, "Title", "title", "newsTitle")
        if not title:
            continue
        body_html = _child_text(node, "DataContents", "dataContents", "contents", "description")
        items.append({
            "title": strip_html(title),
            "subtitle": strip_html(_child_text(node, "SubTitle1", "subTitle1", "subtitle")),
            "body": strip_html(body_html),
            "ministry": _child_text(node, "MinisterCode", "ministerCode", "minister", "ministry", "deptName", "orgName"),
            "url": _child_text(node, "OriginalUrl", "originalUrl", "url", "link"),
            "date": base.parse_date(_child_text(node, "ApproveDate", "approveDate", "pubDate", "regDate", "ModifyDate")),
            "license": _child_text(node, "Kogl", "kogl", "License", "license", "Copyright", "copyright", "koglType"),
        })
    return items, int(total)


def parse_rss(text: str) -> list[dict[str, Any]]:
    """korea.kr RSS → items (title, body=description, ministry=author/dc:creator/category, url=link, date=pubDate)."""
    try:
        root = ET.fromstring(text.lstrip())
    except ET.ParseError as exc:
        raise CollectorError(f"RSS 파싱 실패: {text[:200]!r}") from exc
    items: list[dict[str, Any]] = []
    for node in root.iter("item"):
        title = strip_html(node.findtext("title"))
        if not title:
            continue
        ministry = ""
        for tag in ("author", "{http://purl.org/dc/elements/1.1/}creator", "category", "source"):
            ministry = (node.findtext(tag) or "").strip()
            if ministry:
                break
        items.append({
            "title": title, "subtitle": "",
            "body": strip_html(node.findtext("description")),
            "ministry": ministry,
            "url": (node.findtext("link") or "").strip(),
            "date": base.parse_date(node.findtext("pubDate")),
            "license": "",
        })
    return items


def select_and_convert(items: list[dict[str, Any]], rng: DateRange | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """부처·키워드·공공누리 필터를 적용해 PolicyEvent dict 목록과 건너뛴 사유별 개수를 돌려준다."""
    events: list[dict[str, Any]] = []
    skipped = {"skipped_no_ministry": 0, "skipped_no_keyword": 0, "skipped_no_license": 0, "skipped_no_date": 0, "skipped_out_of_range": 0}
    for it in items:
        d = it.get("date")
        if d is None:
            skipped["skipped_no_date"] += 1
            continue
        if rng and not (rng.since <= d <= rng.until):
            skipped["skipped_out_of_range"] += 1
            continue
        text = " ".join(filter(None, [it.get("title"), it.get("subtitle"), it.get("body")]))
        ministry = match_ministry(it.get("ministry"), it.get("title"), it.get("body"))
        if not ministry:
            skipped["skipped_no_ministry"] += 1
            continue
        typ = classify(text)
        if not typ:
            skipped["skipped_no_keyword"] += 1
            continue
        lic = detect_kogl(it.get("license"), it.get("body"), it.get("page_text"))
        if not lic:
            skipped["skipped_no_license"] += 1
            continue
        value, value_text = extract_value(text)
        summary = it.get("subtitle") or base.clip(it.get("body"), 300)
        events.append({
            "event_id": make_event_id(it.get("url"), it["title"], d),
            "country": "KR", "type": typ, "title": it["title"], "summary": summary,
            "targets": extract_targets(text), "value": value, "value_text": value_text,
            "announced_at": d, "source": SOURCE, "source_url": it.get("url") or RSS_URL,
            "license": f"{lic} — 출처: {ministry} / 대한민국 정책브리핑(korea.kr)",
            "raw_text": it.get("body") or "", "is_demo": False,
        })
    return events, skipped


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------

def fetch_api(client: httpx.Client, service_key: str, rng: DateRange) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    url = None
    last_exc: Exception | None = None
    for page in range(1, MAX_PAGES + 1):
        params = {"serviceKey": service_key, "startDate": base.yyyymmdd(rng.since), "endDate": base.yyyymmdd(rng.until),
                  "pageNo": page, "numOfRows": PAGE_SIZE}
        if url is None:
            # 첫 페이지: 후보 주소를 차례로 시도
            for cand in API_CANDIDATES:
                try:
                    resp = base.get(client, cand, params, retries=1)
                    got, total = parse_press_release_xml(resp.text)
                    url = cand
                    log.info("정책브리핑 API 사용: %s", cand)
                    break
                except CollectorError as exc:
                    last_exc = exc
                    log.warning("정책브리핑 API 실패 %s: %s", cand, str(exc)[:160])
            if url is None:
                raise CollectorError(f"정책브리핑 API 주소를 찾지 못함: {last_exc}")
        else:
            resp = base.get(client, url, params)
            got, total = parse_press_release_xml(resp.text)
        items.extend(got)
        if not got or (total and len(items) >= total):
            break
    return items


def fetch_rss(client: httpx.Client, *, fetch_pages: bool = True) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    last_exc: Exception | None = None
    for url in RSS_CANDIDATES:
        try:
            resp = base.get(client, url, retries=1)
            if "<rss" not in resp.text[:2000] and "<feed" not in resp.text[:2000]:
                raise CollectorError(f"RSS 형식이 아님: {url}")
            items = parse_rss(resp.text)
            log.info("RSS 사용: %s (%d건)", url, len(items))
            break
        except CollectorError as exc:
            last_exc = exc
            log.warning("RSS 실패 %s: %s", url, str(exc)[:120])
    if not items and last_exc is not None:
        raise MissingApiKey("korea.kr RSS 주소를 찾지 못했습니다. 공공데이터포털 '문화체육관광부_대한민국 정책브리핑' API 활용신청 후 "
                            "DATA_GO_KR_API_KEY 로 수집하세요 (RSS 는 폴백).")
    if fetch_pages:
        fetched = 0
        for it in items:
            if fetched >= MAX_PAGE_FETCH or not it.get("url"):
                break
            text = " ".join(filter(None, [it.get("title"), it.get("body")]))
            if not classify(text):  # 키워드가 없는 기사는 페이지를 받지 않는다
                continue
            try:
                page = base.get(client, it["url"], retries=1)
                it["page_text"] = strip_html(page.text)
                fetched += 1
            except CollectorError as exc:
                log.warning("기사 페이지 조회 실패 %s: %s", it["url"], exc)
    return items


def run(session: Session, rng: DateRange, *, api_key: str | None = None,
        client: httpx.Client | None = None, **_: Any) -> dict[str, Any]:
    key = api_key or settings.data_go_kr_api_key
    own = client is None
    client = client or base.make_client()
    try:
        if key:
            from .krx_prices import normalize_service_key
            mode = "data.go.kr API"
            try:
                items = fetch_api(client, normalize_service_key(key), rng)
            except CollectorError as exc:
                log.warning("보도자료 API 실패 (%s) — RSS 로 폴백", exc)
                mode, items = "RSS (API 실패 폴백)", fetch_rss(client)
        else:
            log.info("DATA_GO_KR_API_KEY 없음 — korea.kr RSS 로 수집 (최근 자료만)")
            mode, items = "RSS", fetch_rss(client)
    finally:
        if own:
            client.close()
    events, skipped = select_and_convert(items, rng)
    n = base.upsert_events(session, events)
    log.info("정책브리핑 [%s]: 항목 %d건 → 이벤트 %d건, 건너뜀 %s", mode, len(items), n, skipped)
    return {"mode": mode, "items": len(items), "events": n, **{k: v for k, v in skipped.items() if v}}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    base.add_range_args(ap)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from app.db import init_db, session_scope

    init_db()
    rng = base.resolve_range(args.since, args.until, default_since=date.today() - timedelta(days=DEFAULT_DAYS))
    with session_scope() as s:
        print(run(s, rng))


if __name__ == "__main__":
    main()
