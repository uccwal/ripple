"""미국 관보(Federal Register) API 수집기 — 관세·수입규제 관련 문서를 PolicyEvent 로 저장.

    PYTHONPATH=backend:. python -m collectors.federal_register --since 2025-01-01

API: https://www.federalregister.gov/api/v1/documents.json  (API 키 불필요)
  검색 조건: conditions[term]=…, conditions[agencies][]=trade-representative|commerce-department|international-trade-administration,
            conditions[type][]=PRESDOCU|RULE, conditions[publication_date][gte|lte]=YYYY-MM-DD, per_page, page, order=newest
  응답: {"count": N, "total_pages": k, "next_page_url": …,
         "results": [{"document_number": "2025-01234", "title": …, "abstract": …, "type": "Presidential Document",
                      "publication_date": "2025-04-02", "html_url": …, "body_html_url": …, "agencies": [{"name": …, "slug": …}]}]}
  검색어마다 따로 조회한 뒤 document_number 로 중복을 제거한다.

저장 규칙
  event_id="fr_"+document_number, country="US", type=tariff|regulation (키워드), summary=abstract, raw_text=abstract(+본문 링크),
  announced_at=publication_date, source="Federal Register", source_url=html_url, is_demo=False,
  license="Public domain (U.S. Government work) — 관보 로고·인장 사용 금지" (44 U.S.C. §1506, 1 CFR 2.6 참고).
  value/value_text: 초록에서 "N percent" / "N%" 를 정규식으로 찾으면 채운다 (첫 번째 값).

주의: 네트워크가 차단된 환경에서 작성되어 실제 호출을 검증하지 못했다. 키 없이 바로 스모크 테스트 가능하다.
"""
from __future__ import annotations

import argparse
import logging
import re
from datetime import date, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from . import base
from .base import CollectorError, DateRange

log = logging.getLogger("collectors.federal_register")

REQUIRED_KEY = None  # API 키 불필요
DEFAULT_DAYS = 365
BASE_URL = "https://www.federalregister.gov/api/v1/documents.json"
SOURCE = "Federal Register"
LICENSE = "Public domain (U.S. Government work) — 관보 로고·인장(seal) 사용 금지, 출처(Federal Register, 문서번호) 표시"
PER_PAGE = 100
MAX_PAGES = 20  # 검색어당 상한 (과도한 수집 방지)

# 검색어·기관·문서유형 (편집 가능)
SEARCH_TERMS: list[str] = ["tariff", "duties", "\"Section 232\"", "\"Section 301\"", "\"import restriction\""]
# Federal Register 기관 slug. USTR 의 slug 는 "trade-representative-office-of-united-states" 다.
# slug 가 틀리면 API 가 400 {"errors":{"agencies":"invalid value"}} 을 돌려주므로, 그 경우 기관 필터 없이 다시 조회한다.
AGENCIES: list[str] = ["trade-representative-office-of-united-states", "commerce-department", "international-trade-administration"]
DOC_TYPES: list[str] = ["PRESDOCU", "RULE"]
FIELDS: list[str] = ["document_number", "title", "abstract", "type", "publication_date", "html_url",
                     "body_html_url", "agencies", "action", "subtype"]

# 유형 분류: 관세 관련 키워드가 있으면 tariff, 아니면 regulation (금리 이벤트는 관보에서 수집하지 않음)
TARIFF_KEYWORDS = ("tariff", "duty", "duties", "section 232", "section 301", "antidumping", "anti-dumping",
                   "countervailing", "ad valorem", "import quota", "trade remedy", "reciprocal trade")
# 대상 품목 → targets (demo_events.json 의 어휘와 맞춤)
TARGET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "semiconductor": ("semiconductor", "chip", "integrated circuit"),
    "semiconductor_equipment": ("semiconductor manufacturing equipment", "lithography"),
    "display": ("display panel", "oled", "lcd"),
    "automobile": ("automobile", "passenger vehicle", "light truck", "auto part"),
    "steel": ("steel",),
    "aluminum": ("aluminum", "aluminium"),
    "battery": ("battery", "lithium-ion"),
    "pharmaceutical": ("pharmaceutical", "drug"),
    "agriculture": ("agricultur", "beef", "rice", "soybean"),
    "all_imports": ("all imports", "all articles imported", "reciprocal tariff", "all trading partners"),
}
_PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent(?:age point)?s?)", re.IGNORECASE)


# ----------------------------------------------------------------------------
# 파싱 (HTTP 와 분리)
# ----------------------------------------------------------------------------

def classify(text: str) -> str:
    t = text.lower()
    return "tariff" if any(k in t for k in TARIFF_KEYWORDS) else "regulation"


def extract_targets(text: str) -> list[str]:
    t = text.lower()
    return [tgt for tgt, kws in TARGET_KEYWORDS.items() if any(k in t for k in kws)]


def extract_percent(text: str) -> tuple[float | None, str]:
    """초록에서 첫 'N percent' / 'N%' → (N, 'N%'). 없으면 (None, '')."""
    m = _PERCENT_RE.search(text or "")
    if not m:
        return None, ""
    v = base.to_float(m.group(1))
    if v is None:
        return None, ""
    txt = f"{v:g}%p" if "point" in m.group(0).lower() else f"{v:g}%"
    return v, txt


def document_to_event(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Federal Register 문서 1건 → PolicyEvent dict. 필수 필드가 없으면 None."""
    num = doc.get("document_number")
    pub = base.parse_date(doc.get("publication_date"))
    title = (doc.get("title") or "").strip()
    if not num or pub is None or not title:
        return None
    abstract = (doc.get("abstract") or "").strip()
    text = f"{title}\n{abstract}"
    value, value_text = extract_percent(abstract or title)
    agencies = [a.get("name") for a in doc.get("agencies") or [] if isinstance(a, dict) and a.get("name")]
    body_url = doc.get("body_html_url") or ""
    raw_parts = [abstract or "(초록 없음)"]
    if agencies:
        raw_parts.append("기관: " + ", ".join(agencies))
    if doc.get("type"):
        raw_parts.append(f"문서 유형: {doc['type']}" + (f" / {doc['subtype']}" if doc.get("subtype") else ""))
    if body_url:
        raw_parts.append(f"본문: {body_url}")
    return {
        "event_id": f"fr_{num}",
        "country": "US",
        "type": classify(text),
        "title": title,
        "summary": abstract,
        "targets": extract_targets(text),
        "value": value,
        "value_text": value_text,
        "announced_at": pub,
        "source": SOURCE,
        "source_url": doc.get("html_url") or "",
        "license": LICENSE,
        "raw_text": "\n\n".join(raw_parts),
        "is_demo": False,
    }


def parse_documents(payload: Any) -> tuple[list[dict[str, Any]], int, str | None]:
    """documents.json 응답 → (results, count, next_page_url)."""
    if not isinstance(payload, dict):
        raise CollectorError(f"Federal Register 응답 형식이 아님: {type(payload).__name__}")
    if "errors" in payload:
        raise CollectorError(f"Federal Register 오류: {payload['errors']}")
    results = [r for r in payload.get("results", []) or [] if isinstance(r, dict)]
    return results, int(payload.get("count", 0) or 0), payload.get("next_page_url")


def build_params(term: str, rng: DateRange, page: int = 1, *, with_agencies: bool = True) -> list[tuple[str, Any]]:
    """배열 파라미터(conditions[agencies][] 등)는 같은 키를 반복해야 하므로 (key, value) 목록으로 만든다."""
    params: list[tuple[str, Any]] = [
        ("conditions[term]", term),
        ("conditions[publication_date][gte]", rng.since.isoformat()),
        ("conditions[publication_date][lte]", rng.until.isoformat()),
        ("per_page", PER_PAGE), ("page", page), ("order", "newest"),
    ]
    if with_agencies:
        params += [("conditions[agencies][]", a) for a in AGENCIES]
    params += [("conditions[type][]", t) for t in DOC_TYPES]
    params += [("fields[]", f) for f in FIELDS]
    return params


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------

def fetch_documents(client: httpx.Client, rng: DateRange, terms: list[str] | None = None) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    with_agencies = True
    for term in terms or SEARCH_TERMS:
        for page in range(1, MAX_PAGES + 1):
            try:
                payload = base.get_json(client, BASE_URL, build_params(term, rng, page, with_agencies=with_agencies))
            except CollectorError as exc:
                if with_agencies and "agencies" in str(exc):
                    log.warning("기관 slug 가 거부됨 — 기관 필터 없이 재조회: %s", exc)
                    with_agencies = False
                    payload = base.get_json(client, BASE_URL, build_params(term, rng, page, with_agencies=False))
                else:
                    raise
            results, count, next_url = parse_documents(payload)
            for doc in results:
                num = doc.get("document_number")
                if num and num not in seen:
                    seen[num] = doc
            if not next_url or not results:
                break
        log.info("검색어 %s: 누적 %d건", term, len(seen))
    return list(seen.values())


def run(session: Session, rng: DateRange, *, client: httpx.Client | None = None, **_: Any) -> dict[str, Any]:
    own = client is None
    client = client or base.make_client()
    try:
        docs = fetch_documents(client, rng)
    finally:
        if own:
            client.close()
    events = [e for e in (document_to_event(d) for d in docs) if e]
    n = base.upsert_events(session, events)
    by_type = {t: sum(1 for e in events if e["type"] == t) for t in ("tariff", "regulation")}
    log.info("Federal Register: 문서 %d건 → 이벤트 %d건 (%s)", len(docs), n, by_type)
    return {"documents": len(docs), "events": n, **by_type}


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
