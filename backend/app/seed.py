"""초기 데이터 적재: 테이블 생성, 가상 포트폴리오, 초기 정책 이벤트, (선택) 합성 시계열.

    python -m app.seed               # 포트폴리오·이벤트만 (시계열은 collectors로 수집)
    python -m app.seed --synthetic   # 시계열이 없으면 데모용 합성 시계열도 적재
    python -m app.seed --synthetic --force   # 합성 시계열로 덮어쓰기
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime

from sqlalchemy import delete, func, select

from .util import utcnow
from .config import DATA_DIR
from .db import init_db, session_scope
from .models.tables import Holding, PolicyEvent, Portfolio, Series, SeriesValue
from . import synthetic


def load_portfolios(s) -> int:
    data = json.loads((DATA_DIR / "portfolios.json").read_text(encoding="utf-8"))
    for p in data["portfolios"]:
        s.merge(Portfolio(portfolio_id=p["portfolio_id"], name=p["name"], base_currency=p["base_currency"],
                          description=p["description"], aum=p["aum"]))
        s.execute(delete(Holding).where(Holding.portfolio_id == p["portfolio_id"]))
        for h in p["holdings"]:
            s.add(Holding(portfolio_id=p["portfolio_id"], asset_id=h["asset_id"], name=h["name"],
                          asset_class=h["asset_class"], weight=h["weight"], currency=h["currency"],
                          sector=h["sector"], pricing=h["pricing"], factors=h["factors"]))
    return len(data["portfolios"])


def load_events(s) -> int:
    data = json.loads((DATA_DIR / "demo_events.json").read_text(encoding="utf-8"))
    for e in data["events"]:
        s.merge(PolicyEvent(
            event_id=e["event_id"], country=e["country"], type=e["type"], title=e["title"], summary=e["summary"],
            targets=e["targets"], value=e["value"], value_text=e["value_text"],
            announced_at=date.fromisoformat(e["announced_at"]), source=e["source"], source_url=e["source_url"],
            raw_text=e["raw_text"], is_demo=e["is_demo"],
            license="시연용 예시 (가상)" if e["is_demo"] else "공개 발표 내용 요약",
        ))
    return len(data["events"])


def load_synthetic(s, force: bool) -> int:
    """합성 시계열 적재. 이미 실제 수집 데이터가 있는 DB 에는 (force 가 아니면) 새 시리즈라도 합성을 넣지 않는다 —
    팩터를 추가한 뒤 재배포해도 '합성 데이터' 배지가 다시 뜨지 않게 하고, 빈 시리즈는 수집기가 전체 기간으로 채운다."""
    if not force:
        has_real = s.scalar(select(func.count()).select_from(Series).where(~Series.source.like("SYNTHETIC%")))
        if has_real:
            return 0
    series = synthetic.generate()
    specs = {sid: (name, unit) for sid, name, unit, _ in synthetic.FACTOR_SPECS + synthetic.ASSET_SPECS}
    now = utcnow()
    written = 0
    for sid, values in series.items():
        exists = s.scalar(select(func.count()).select_from(SeriesValue).where(SeriesValue.series_id == sid))
        existing = s.get(Series, sid)
        if exists and not force and existing and not existing.source.startswith("SYNTHETIC"):
            continue  # 실제 수집 데이터는 덮어쓰지 않는다
        if exists and not force:
            continue
        name, unit = specs[sid]
        s.merge(Series(series_id=sid, name=name, source="SYNTHETIC", unit=unit, frequency="D",
                       license=synthetic.SYNTHETIC_LICENSE, source_url=""))
        s.execute(delete(SeriesValue).where(SeriesValue.series_id == sid))
        s.bulk_save_objects([SeriesValue(series_id=sid, date=d.date(), value=float(v), collected_at=now)
                             for d, v in values.items()])
        written += 1
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", help="시계열이 없으면 합성 시계열 적재")
    ap.add_argument("--force", action="store_true", help="합성 시계열로 덮어쓰기 (실제 수집 데이터 포함)")
    args = ap.parse_args()
    init_db()
    with session_scope() as s:
        print(f"portfolios: {load_portfolios(s)}")
        print(f"events: {load_events(s)}")
        if args.synthetic:
            print(f"synthetic series written: {load_synthetic(s, args.force)}")


if __name__ == "__main__":
    main()
