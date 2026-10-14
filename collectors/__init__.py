"""RIPPLE 데이터 수집기 패키지.

실행 방법 (저장소 루트에서):

    PYTHONPATH=backend:. python -m collectors.run_all [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--only fred,ecos]

구성
- base.py              공통 HTTP 세션(재시도·타임아웃), upsert_series / upsert_events, 날짜·인자 도우미
- fred.py              FRED API            → DGS10, WTI
- ecos.py              한국은행 ECOS API    → USDKRW, KTB3Y, (선택) BOK_BASE_RATE
- krx_prices.py        공공데이터포털 금융위원회 시세 API → KOSPI, KOSPI_IT, KR_K200, US_EQ, US_TECH, KR_SEMI, KR_AUTO
- federal_register.py  Federal Register API → PolicyEvent (US 관세·규제)
- korea_briefing.py    대한민국 정책브리핑   → PolicyEvent (KR 관세·수출통제·기준금리·규제)
- run_all.py           전체 실행 CLI

원칙 (docs/DESIGN.md 4장)
- 모든 시리즈·이벤트에 source, source_url, license, collected_at 을 남긴다.
- 제3자 저작권 지수(S&P 500 등)는 수집하지 않고 국내 상장 ETF로 대체한다.
- 합성 시계열(source="SYNTHETIC")은 같은 series_id 의 실제 데이터가 수집되면 대체된다.
- 모든 수집기는 멱등(idempotent)이다: 같은 구간을 다시 수집해도 값이 갱신될 뿐 중복 행이 생기지 않는다.

주의: 이 패키지는 외부 네트워크가 차단된 환경에서 작성되어 실제 엔드포인트 호출은 검증하지 못했다.
API 키를 넣고 `--only` 로 수집기별 스모크 테스트를 먼저 수행할 것. 응답 파싱 로직은 collectors/tests 로 검증한다.
"""
from __future__ import annotations

__all__ = ["base", "fred", "ecos", "krx_prices", "federal_register", "korea_briefing", "run_all"]
