"""수집한 시계열에서 정책 이벤트를 파생한다 (텍스트 소스 없이도 확실한 기준금리 결정 이벤트).

- 한국은행 기준금리(BOK_BASE_RATE, ECOS 722Y001): 값이 바뀐 날 = 금통위 결정 → PolicyEvent(country=KR, type=rate)
- 미국 연방기금 목표금리 상단(FED_TARGET_UPPER, FRED DFEDTARU): 값이 바뀐 날 = FOMC 결정 → PolicyEvent(country=US, type=rate)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select

from .db import session_scope
from .models.tables import PolicyEvent, Series, SeriesValue
from .util import utcnow

log = logging.getLogger("ripple.derive")


@dataclass(frozen=True)
class RateSpec:
    series_id: str
    prefix: str  # event_id 접두사
    country: str
    bank: str  # 제목에 쓰는 기관명
    body: str  # 결정 기구
    source: str
    source_url: str
    level_label: str = ""  # "상단" 등 수준 표기 접두


BOK = RateSpec("BOK_BASE_RATE", "bok_rate", "KR", "한국은행 기준금리", "금융통화위원회",
               "한국은행 ECOS (기준금리 시계열에서 파생)", "https://ecos.bok.or.kr")
FED = RateSpec("FED_TARGET_UPPER", "fed_rate", "US", "미국 연준 기준금리", "FOMC",
               "FRED (연방기금 목표금리 상단 시계열에서 파생)", "https://fred.stlouisfed.org/series/DFEDTARU", level_label="상단 ")


def derive_rate_events(spec: RateSpec) -> dict:
    """spec.series_id 시계열의 변화일마다 기준금리 결정 이벤트를 만든다. 반환: {"created": n, "total": m}"""
    created = 0
    total = 0
    with session_scope() as s:
        meta = s.get(Series, spec.series_id)
        if meta is None or meta.source.startswith("SYNTHETIC"):
            return {"created": 0, "total": 0, "skipped": f"{spec.series_id} 없음"}
        rows = s.execute(select(SeriesValue.date, SeriesValue.value).where(SeriesValue.series_id == spec.series_id)
                         .order_by(SeriesValue.date)).all()
        prev = None
        for d, v in rows:
            if prev is not None and abs(v - prev) > 1e-9:
                total += 1
                delta = v - prev
                eid = f"{spec.prefix}_{d.strftime('%Y%m%d')}"
                if s.get(PolicyEvent, eid) is None:
                    direction = "인상" if delta > 0 else "인하"
                    s.add(PolicyEvent(
                        event_id=eid, country=spec.country, type="rate",
                        title=f"{spec.bank} {abs(delta):.2f}%p {direction} ({spec.level_label}{v:.2f}%)",
                        summary=f"{spec.body} 기준금리 결정: {spec.level_label}{prev:.2f}% → {v:.2f}%",
                        targets=["policy_rate"], value=round(delta, 4), value_text=f"{'+' if delta > 0 else '−'}{abs(delta):.2f}%p",
                        announced_at=d, source=spec.source, source_url=spec.source_url,
                        license=meta.license or "출처 표시",
                        raw_text=(f"{spec.bank}가 {d.isoformat()}에 {spec.level_label}{prev:.2f}%에서 {v:.2f}%로 {direction}됐다. "
                                  f"({spec.series_id} 시계열의 변화일에서 자동 생성, 결정 기구 {spec.body})"),
                        is_demo=False, relevance="high", title_orig=None, collected_at=utcnow(),
                    ))
                    created += 1
            prev = v
    log.info("%s 이벤트: 신규 %d건 / 전체 %d건", spec.bank, created, total)
    return {"created": created, "total": total}


def derive_bok_rate_events() -> dict:
    return derive_rate_events(BOK)


def derive_fed_rate_events() -> dict:
    return derive_rate_events(FED)
