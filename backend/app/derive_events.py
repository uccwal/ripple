"""수집한 시계열에서 정책 이벤트를 파생한다 (텍스트 소스 없이도 확실한 한국 정책 이벤트).

- 한국은행 기준금리(BOK_BASE_RATE, ECOS 722Y001): 값이 바뀐 날 = 금통위 결정 → PolicyEvent(country=KR, type=rate)
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from .db import session_scope
from .models.tables import PolicyEvent, Series, SeriesValue
from .util import utcnow

log = logging.getLogger("ripple.derive")


def derive_bok_rate_events() -> dict:
    """BOK_BASE_RATE 시계열의 변화일마다 기준금리 결정 이벤트를 만든다. 반환: {"created": n, "total": m}"""
    created = 0
    total = 0
    with session_scope() as s:
        meta = s.get(Series, "BOK_BASE_RATE")
        if meta is None or meta.source.startswith("SYNTHETIC"):
            return {"created": 0, "total": 0, "skipped": "BOK_BASE_RATE 없음"}
        rows = s.execute(select(SeriesValue.date, SeriesValue.value).where(SeriesValue.series_id == "BOK_BASE_RATE")
                         .order_by(SeriesValue.date)).all()
        prev = None
        for d, v in rows:
            if prev is not None and abs(v - prev) > 1e-9:
                total += 1
                delta = v - prev
                eid = f"bok_rate_{d.strftime('%Y%m%d')}"
                if s.get(PolicyEvent, eid) is None:
                    direction = "인상" if delta > 0 else "인하"
                    s.add(PolicyEvent(
                        event_id=eid, country="KR", type="rate",
                        title=f"한국은행 기준금리 {abs(delta):.2f}%p {direction} ({v:.2f}%)",
                        summary=f"금융통화위원회 기준금리 결정: {prev:.2f}% → {v:.2f}%",
                        targets=["policy_rate"], value=round(delta, 4), value_text=f"{'+' if delta > 0 else '−'}{abs(delta):.2f}%p",
                        announced_at=d, source="한국은행 ECOS (기준금리 시계열에서 파생)",
                        source_url="https://ecos.bok.or.kr", license=meta.license or "한국은행 ECOS 이용약관 — 출처 표시",
                        raw_text=(f"한국은행 기준금리가 {d.isoformat()}에 {prev:.2f}%에서 {v:.2f}%로 {direction}됐다. "
                                  "(ECOS 722Y001 기준금리 시계열의 변화일에서 자동 생성)"),
                        is_demo=False, relevance="high", title_orig=None, collected_at=utcnow(),
                    ))
                    created += 1
            prev = v
    log.info("기준금리 이벤트: 신규 %d건 / 전체 %d건", created, total)
    return {"created": created, "total": total}
