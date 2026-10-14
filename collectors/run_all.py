"""모든 수집기를 순서대로 실행하는 CLI.

    PYTHONPATH=backend:. python -m collectors.run_all
    PYTHONPATH=backend:. python -m collectors.run_all --since 2024-01-01 --only fred,ecos
    PYTHONPATH=backend:. python -m collectors.run_all --list

- API 키가 없는 수집기는 어떤 환경 변수가 필요한지 알려주고 건너뛴다 (실패 아님).
- 수집기마다 결과 개수를 로그로 남기고, 마지막에 요약표를 출력한다.
- 종료 코드는 예상치 못한 예외(버그, DB 오류 등)가 하나라도 있을 때만 1 이다.
  API 오류 응답·네트워크 실패(CollectorError)는 'error' 로 기록하고 다른 수집기는 계속 실행하되 종료 코드는 0 이다.
  cron 에서 이런 오류도 감지하려면 --strict 를 붙인다 (그러면 종료 코드 1).
- 하루 1회 실행을 가정한다 (cron / GitHub Actions 등). 수집기는 멱등이므로 겹치는 구간을 다시 받아도 안전하다.

주의: 네트워크가 차단된 환경에서 작성되어 실제 호출을 검증하지 못했다. 키를 넣고 `--only` 로 수집기별 스모크 테스트부터 할 것.
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from . import base, ecos, federal_register, fred, korea_briefing, krx_prices
from .base import CollectorError, DateRange, MissingApiKey, RunReport

log = logging.getLogger("collectors.run_all")

# settings 속성 → 환경 변수 이름 (건너뜀 메시지용)
ENV_NAMES = {"fred_api_key": "FRED_API_KEY", "ecos_api_key": "ECOS_API_KEY", "data_go_kr_api_key": "DATA_GO_KR_API_KEY"}


@dataclass(frozen=True)
class Collector:
    name: str
    run: Callable[..., dict[str, Any]]
    required_key: str | None  # settings 속성 이름, None 이면 키 불필요
    default_since: date | Callable[[], date]
    description: str

    def since_default(self) -> date:
        return self.default_since() if callable(self.default_since) else self.default_since


REGISTRY: list[Collector] = [
    Collector("fred", fred.run, fred.REQUIRED_KEY, fred.DEFAULT_SINCE, "FRED → DGS10, WTI"),
    Collector("ecos", ecos.run, ecos.REQUIRED_KEY, ecos.DEFAULT_SINCE, "한국은행 ECOS → USDKRW, KTB3Y, (BOK_BASE_RATE)"),
    Collector("krx_prices", krx_prices.run, krx_prices.REQUIRED_KEY, krx_prices.DEFAULT_SINCE,
              "공공데이터포털 금융위원회 시세 → KOSPI, KOSPI_IT, KR_K200, US_EQ, US_TECH, KR_SEMI, KR_AUTO"),
    Collector("federal_register", federal_register.run, federal_register.REQUIRED_KEY,
              lambda: date.today() - timedelta(days=federal_register.DEFAULT_DAYS), "Federal Register → PolicyEvent(US)"),
    Collector("korea_briefing", korea_briefing.run, korea_briefing.REQUIRED_KEY,
              lambda: date.today() - timedelta(days=korea_briefing.DEFAULT_DAYS), "대한민국 정책브리핑 → PolicyEvent(KR)"),
]
NAMES = [c.name for c in REGISTRY]


def key_missing(collector: Collector, settings_obj: Any) -> str | None:
    """키가 필요한데 없으면 환경 변수 이름을, 아니면 None 을 돌려준다."""
    if not collector.required_key:
        return None
    if getattr(settings_obj, collector.required_key, None):
        return None
    return ENV_NAMES.get(collector.required_key, collector.required_key.upper())


def run_one(collector: Collector, session_factory: Callable[[], Any], since: date | None, until: date | None,
            settings_obj: Any) -> RunReport:
    """수집기 하나를 자기 세션(트랜잭션)에서 실행한다. 한 수집기가 실패해도 다른 수집기의 커밋에 영향을 주지 않는다."""
    missing = key_missing(collector, settings_obj)
    if missing:
        return RunReport(collector.name, "skipped", f"{missing} 가 설정되지 않아 건너뜀 (.env 에 추가)")
    rng = base.resolve_range(since, until, default_since=collector.since_default())
    try:
        with session_factory() as s:
            counts = collector.run(s, rng)
        return RunReport(collector.name, "ok", f"{rng.since}~{rng.until}", counts)
    except MissingApiKey as exc:
        return RunReport(collector.name, "skipped", str(exc))
    except CollectorError as exc:
        log.error("[%s] 수집 오류: %s", collector.name, exc)
        return RunReport(collector.name, "error", str(exc))
    except Exception as exc:  # noqa: BLE001 — 예상치 못한 예외: 기록하고 계속, 종료 코드 1
        log.error("[%s] 예상치 못한 예외: %s\n%s", collector.name, exc, traceback.format_exc())
        return RunReport(collector.name, "error", f"{type(exc).__name__}: {exc}", {"unexpected": True})


def parse_only(value: str | None) -> list[str]:
    if not value:
        return list(NAMES)
    names = [v.strip() for v in value.split(",") if v.strip()]
    unknown = [n for n in names if n not in NAMES]
    if unknown:
        raise SystemExit(f"알 수 없는 수집기: {unknown}. 가능: {NAMES}")
    return names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m collectors.run_all", description="RIPPLE 데이터 수집기 일괄 실행")
    base.add_range_args(ap)
    ap.add_argument("--only", help="쉼표로 구분한 수집기 이름 (예: fred,ecos). 기본: 전부")
    ap.add_argument("--list", action="store_true", help="수집기 목록과 필요한 키만 출력")
    ap.add_argument("--strict", action="store_true", help="API·네트워크 오류(CollectorError)도 종료 코드 1 로 (cron 감시용)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from app.config import settings

    if args.list:
        for c in REGISTRY:
            key = ENV_NAMES.get(c.required_key or "", "불필요") if c.required_key else "불필요"
            state = "" if not key_missing(c, settings) else "  (키 없음 → 건너뜀)"
            print(f"{c.name:18s} {c.description:70s} 키: {key}{state}")
        return 0

    from app.db import init_db, session_scope

    init_db()
    reports: list[RunReport] = []
    for c in REGISTRY:
        if c.name not in parse_only(args.only):
            continue
        log.info("▶ %s — %s", c.name, c.description)
        rep = run_one(c, session_scope, args.since, args.until, settings)
        log.info(rep.line())
        reports.append(rep)

    print("\n=== 수집 요약 ===")
    for rep in reports:
        print(rep.line())
    errors = [r for r in reports if r.status == "error"]
    unexpected = [r for r in errors if r.counts.get("unexpected")]
    if errors:
        print(f"\n오류 {len(errors)}건: {', '.join(r.collector for r in errors)}"
              + (f" (예상치 못한 예외 {len(unexpected)}건)" if unexpected else ""))
    if unexpected or (args.strict and errors):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
