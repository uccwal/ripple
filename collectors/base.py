"""수집기 공통 도우미.

- HTTP: 재시도·타임아웃이 설정된 httpx 클라이언트와 `get()` / `get_json()` 래퍼
- DB:   `upsert_series()` (Series 메타 병합 + SeriesValue 갱신/삽입), `upsert_events()` (PolicyEvent 병합)
- 날짜: `parse_date()` (YYYY-MM-DD / YYYYMMDD / YYYY.MM.DD / ISO datetime), `to_float()` (FRED "." 결측 등)
- CLI:  `add_range_args()` / `resolve_range()` (--since / --until)

파싱 로직은 HTTP와 분리해 두어 collectors/tests 에서 고정 응답(fixture)으로 검증한다.
"""
from __future__ import annotations

import argparse
import logging
import math
import re
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from app.models.tables import PolicyEvent, Series, SeriesValue

log = logging.getLogger("collectors")

USER_AGENT = "RIPPLE-collector/0.1 (KIC AI agent competition entry; data collection for research/demo)"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
RETRY_STATUSES = {429, 500, 502, 503, 504}


_SECRET_PARAM = re.compile(r"((?:serviceKey|api_key|apiKey|key)=)[^&\s'\"]+", re.IGNORECASE)


def redact(text: str) -> str:
    """URL·오류 문구에 들어간 API 키를 가린다 (수집 보고서는 공개 화면에 표시된다)."""
    return _SECRET_PARAM.sub(r"\1***", str(text))


class CollectorError(RuntimeError):
    """수집기에서 예상 가능한 오류 (API 오류 응답, 파싱 실패 등)."""


class MissingApiKey(CollectorError):
    """필요한 API 키가 환경 변수에 없을 때. run_all 은 이 예외를 '건너뜀'으로 처리한다."""


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------

def make_client(timeout: httpx.Timeout | float = DEFAULT_TIMEOUT, **kwargs: Any) -> httpx.Client:
    """공통 헤더·타임아웃이 설정된 httpx 클라이언트. 테스트에서는 transport=httpx.MockTransport(...) 를 넘긴다."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, application/xml;q=0.9, */*;q=0.8"}
    headers.update(kwargs.pop("headers", {}))
    return httpx.Client(timeout=timeout, headers=headers, follow_redirects=True, **kwargs)


def get(client: httpx.Client, url: str, params: Mapping[str, Any] | None = None, *,
        retries: int = 3, backoff: float = 1.0) -> httpx.Response:
    """GET + 재시도. 네트워크 오류와 429/5xx 는 지수 백오프로 재시도하고, 그 밖의 4xx 는 즉시 예외."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.get(url, params=params)
            if resp.status_code in RETRY_STATUSES and attempt < retries:
                wait = _retry_after(resp) or backoff * (2 ** attempt)
                log.warning("HTTP %s from %s — %.1fs 후 재시도 (%d/%d)", resp.status_code, resp.url, wait, attempt + 1, retries)
                time.sleep(wait)
                continue
            if resp.status_code >= 400:  # 재시도 대상이 아닌 4xx, 또는 재시도를 다 쓴 5xx
                snippet = resp.text[:200].replace("\n", " ")
                raise CollectorError(f"HTTP {resp.status_code} from {redact(str(resp.url))}: {snippet!r}")
            return resp
        except httpx.TransportError as exc:  # 연결·타임아웃 등
            last_exc = exc
            if attempt >= retries:
                break
            wait = backoff * (2 ** attempt)
            log.warning("%s: %s — %.1fs 후 재시도 (%d/%d)", type(exc).__name__, url, wait, attempt + 1, retries)
            time.sleep(wait)
    raise CollectorError(f"요청 실패: {redact(url)} ({redact(last_exc)})") from last_exc


def get_json(client: httpx.Client, url: str, params: Mapping[str, Any] | None = None, **kw: Any) -> Any:
    resp = get(client, url, params, **kw)
    try:
        return resp.json()
    except ValueError as exc:
        snippet = resp.text[:300].replace("\n", " ")
        raise CollectorError(f"JSON 이 아닌 응답: {resp.url} → {snippet!r}") from exc


def _retry_after(resp: httpx.Response) -> float | None:
    ra = resp.headers.get("Retry-After")
    if not ra:
        return None
    try:
        return min(float(ra), 60.0)
    except ValueError:
        return None


# ----------------------------------------------------------------------------
# 값·날짜 파싱
# ----------------------------------------------------------------------------

_MISSING = {"", ".", "-", "na", "n/a", "nan", "null", "none"}


def to_float(raw: Any) -> float | None:
    """문자열 숫자를 float 로. FRED 의 "." 결측, 빈 문자열, 천 단위 쉼표를 처리한다. 결측이면 None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return None if (isinstance(raw, float) and math.isnan(raw)) else float(raw)
    s = str(raw).strip().replace(",", "")
    if s.lower() in _MISSING:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def parse_date(raw: Any) -> date | None:
    """YYYY-MM-DD, YYYYMMDD, YYYY.MM.DD, YYYY/MM/DD, ISO datetime(앞 10자) 을 date 로. 실패하면 None."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    if len(s) == 8 and s.isdigit():
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None
    s10 = s[:10].replace(".", "-").replace("/", "-")
    try:
        return date.fromisoformat(s10)
    except ValueError:
        pass
    for fmt in ("%a, %d %b %Y", "%d %b %Y"):  # RSS pubDate (RFC 822) 앞부분
        try:
            return datetime.strptime(s[:16].strip(), fmt).date()
        except ValueError:
            continue
    return None


def yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def utcnow_naive() -> datetime:
    """DB 컬럼(DateTime, naive)과 맞춘 UTC 현재 시각."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ----------------------------------------------------------------------------
# DB upsert
# ----------------------------------------------------------------------------

@dataclass
class UpsertResult:
    series_id: str
    inserted: int = 0
    updated: int = 0
    skipped: int = 0  # 결측·중복 날짜로 버린 점
    replaced_synthetic: int = 0  # 삭제한 합성 행 수
    first: date | None = None
    last: date | None = None

    @property
    def total(self) -> int:
        return self.inserted + self.updated

    def as_dict(self) -> dict[str, Any]:
        return {"inserted": self.inserted, "updated": self.updated, "skipped": self.skipped,
                "replaced_synthetic": self.replaced_synthetic,
                "range": f"{self.first}~{self.last}" if self.first else ""}


def upsert_series(session: Session, series_id: str, name: str, source: str, unit: str, frequency: str,
                  license: str, source_url: str, points: Iterable[tuple[Any, Any]], *,
                  replace_synthetic: bool = True) -> UpsertResult:
    """Series 메타를 병합하고 (series_id, date) 기준으로 SeriesValue 를 갱신·삽입한다.

    - 같은 날짜가 여러 번 오면 마지막 값을 쓴다. 결측(None/NaN) 은 버린다.
    - 기존 Series 가 SYNTHETIC 이고 새 source 가 실제 출처면 합성 행을 모두 지우고 실제 값만 남긴다
      (합성·실제 값이 한 시리즈에 섞이지 않게 하기 위해). seed.py 는 실제 출처 시리즈를 덮어쓰지 않는다.
    - 갱신·삽입된 모든 행의 collected_at 을 지금(UTC)으로 둔다. 재실행해도 행이 늘지 않는다 (멱등).
    """
    result = UpsertResult(series_id=series_id)
    pts: dict[date, float] = {}
    for raw_d, raw_v in points:
        d = parse_date(raw_d)
        v = to_float(raw_v)
        if d is None or v is None:
            result.skipped += 1
            continue
        if d in pts:
            result.skipped += 1
        pts[d] = v

    existing_meta = session.get(Series, series_id)
    if (existing_meta is not None and replace_synthetic
            and _is_synthetic(existing_meta.source) and not _is_synthetic(source)):
        res = session.execute(delete(SeriesValue).where(SeriesValue.series_id == series_id))
        result.replaced_synthetic = res.rowcount or 0
        log.info("%s: 합성 시계열 %d행 삭제 후 실제 데이터(%s)로 대체", series_id, result.replaced_synthetic, source)

    session.merge(Series(series_id=series_id, name=name, source=source, unit=unit, frequency=frequency,
                         license=license, source_url=source_url))
    session.flush()

    if not pts:
        return result

    dates = sorted(pts)
    result.first, result.last = dates[0], dates[-1]
    rows = session.execute(
        select(SeriesValue.id, SeriesValue.date)
        .where(SeriesValue.series_id == series_id, SeriesValue.date >= dates[0], SeriesValue.date <= dates[-1])
    ).all()
    existing = {_as_date(d): i for i, d in rows}
    now = utcnow_naive()
    updates = [{"id": existing[d], "value": pts[d], "collected_at": now} for d in dates if d in existing]
    inserts = [{"series_id": series_id, "date": d, "value": pts[d], "collected_at": now}
               for d in dates if d not in existing]
    if updates:
        session.execute(update(SeriesValue), updates)
    if inserts:
        session.execute(insert(SeriesValue), inserts)
    session.flush()
    result.inserted, result.updated = len(inserts), len(updates)
    return result


def _is_synthetic(source: str | None) -> bool:
    return (source or "").strip().upper().startswith("SYNTHETIC")


def _as_date(d: Any) -> date:
    return d if isinstance(d, date) and not isinstance(d, datetime) else parse_date(d)  # type: ignore[return-value]


# PolicyEvent 컬럼 길이 (tables.py)
_LEN = {"title": 300, "value_text": 64, "source": 100, "country": 8, "type": 16}


def clip(s: Any, n: int) -> str:
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def upsert_events(session: Session, events: Iterable[Mapping[str, Any]]) -> int:
    """PolicyEvent 를 event_id 기준으로 병합한다. 각 dict 의 키는 PolicyEvent 컬럼과 같다.

    이미 한국어로 구조화된 이벤트(title_orig 가 있음)는 LLM 이 채운 필드(title/summary/type/targets/value/value_text/relevance)를
    덮어쓰지 않고 원문·출처·수집 시각만 갱신한다. 그렇지 않으면 매일 재수집할 때마다 영어 제목으로 되돌아간다.
    relevance 는 수집기가 규칙으로 매긴 값이 있을 때만 쓴다 (LLM 평가가 있으면 그쪽이 우선).
    """
    n = 0
    now = utcnow_naive()
    for e in events:
        announced = parse_date(e.get("announced_at"))
        if not e.get("event_id") or announced is None:
            log.warning("event_id 또는 announced_at 이 없어 건너뜀: %s", e.get("title"))
            continue
        existing = session.get(PolicyEvent, e["event_id"])
        if existing is not None and existing.title_orig:
            existing.announced_at = announced
            existing.source = clip(e.get("source", existing.source), _LEN["source"])
            existing.source_url = e.get("source_url", "") or existing.source_url
            existing.license = e.get("license", "") or existing.license
            existing.raw_text = e.get("raw_text", "") or existing.raw_text
            existing.collected_at = now
            n += 1
            continue
        row = PolicyEvent(
            event_id=e["event_id"],
            country=clip(e.get("country", ""), _LEN["country"]),
            type=clip(e.get("type", "regulation"), _LEN["type"]),
            title=clip(e.get("title", ""), _LEN["title"]),
            summary=e.get("summary", "") or "",
            targets=list(e.get("targets") or []),
            value=e.get("value"),
            value_text=clip(e.get("value_text", ""), _LEN["value_text"]),
            announced_at=announced,
            source=clip(e.get("source", ""), _LEN["source"]),
            source_url=e.get("source_url", "") or "",
            license=e.get("license", "") or "",
            raw_text=e.get("raw_text", "") or "",
            is_demo=bool(e.get("is_demo", False)),
            collected_at=now,
        )
        if e.get("relevance") in ("high", "mid", "low"):
            row.relevance = e["relevance"]
        session.merge(row)
        n += 1
    session.flush()
    return n


# ----------------------------------------------------------------------------
# CLI 인자
# ----------------------------------------------------------------------------

@dataclass
class DateRange:
    since: date
    until: date

    def __post_init__(self) -> None:
        if self.since > self.until:
            raise ValueError(f"--since({self.since}) 가 --until({self.until}) 보다 늦습니다")


def add_range_args(parser: argparse.ArgumentParser, default_since: str | None = None) -> None:
    parser.add_argument("--since", type=_cli_date, default=default_since,
                        help="수집 시작일 YYYY-MM-DD (기본: 수집기별 기본값)")
    parser.add_argument("--until", type=_cli_date, default=None, help="수집 종료일 YYYY-MM-DD (기본: 오늘)")


def _cli_date(s: str) -> date:
    d = parse_date(s)
    if d is None:
        raise argparse.ArgumentTypeError(f"날짜 형식이 아닙니다: {s!r} (YYYY-MM-DD)")
    return d


def resolve_range(since: Any, until: Any, *, default_since: date | str | None = None,
                  default_days: int | None = None) -> DateRange:
    """CLI 값 → DateRange. since 가 없으면 default_since, 그것도 없으면 오늘-default_days(기본 365일)."""
    u = parse_date(until) or date.today()
    s = parse_date(since) or parse_date(default_since)
    if s is None:
        s = u - timedelta(days=default_days or 365)
    return DateRange(s, u)


# ----------------------------------------------------------------------------
# 수집 결과 요약 (run_all 로그용)
# ----------------------------------------------------------------------------

@dataclass
class RunReport:
    collector: str
    status: str = "ok"  # ok | skipped | error
    message: str = ""
    counts: dict[str, Any] = field(default_factory=dict)

    def line(self) -> str:
        parts = [f"[{self.collector}] {self.status}"]
        if self.message:
            parts.append(self.message)
        for k, v in self.counts.items():
            parts.append(f"{k}={v}")
        return " · ".join(parts)
