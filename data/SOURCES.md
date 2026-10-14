# 데이터 출처·라이선스·전처리 (SOURCES)

RIPPLE 이 쓰는 모든 시계열과 정책 이벤트의 출처, 수집기, 수집 주기, 이용 조건, 전처리 방법을 적는다.
설계 기준은 `docs/DESIGN.md` 4장(데이터 모델, 데이터 소스와 라이선스 원칙)이며, 같은 내용이 DB 의 `series.license` /
`policy_event.license` 컬럼과 `collected_at` 에 그대로 기록된다. 제출물의 "데이터 출처·수집일·라이선스·전처리 방법" 기재는 이 문서를 근거로 한다.

> **검증 상태 (2026-10-14 기준)**: 수집기(`collectors/`)는 외부 네트워크가 차단된 환경에서 작성되어 **실제 엔드포인트 호출을 아직 검증하지 못했다.**
> 응답 파싱·DB 적재 로직은 각 API 의 공개 문서 응답 형식을 옮긴 고정 응답으로 `collectors/tests/` 에서 검증했다.
> 키를 넣은 뒤 `python -m collectors.run_all --only <수집기>` 로 스모크 테스트를 하고, 아래 "확인 필요" 항목을 점검해야 한다.

## 1. 시계열 (series / series_value)

수집 주기: **하루 1회** (`PYTHONPATH=backend:. python -m collectors.run_all`, cron 등으로 실행). 모든 수집기는 멱등이라 겹치는 구간을 다시 받아도 중복 행이 생기지 않고 `collected_at` 만 갱신된다.

| series_id | 이름 | 출처 (기관 · API) | 원 자료 ID | 수집기 | 라이선스 / 이용 조건 | 전처리 |
| --- | --- | --- | --- | --- | --- | --- |
| `DGS10` | 미국 국채 10년 금리 (%) | FRED (Federal Reserve Bank of St. Louis) · `fred/series/observations` | `DGS10` — 원 출처 Board of Governors (H.15) | `collectors/fred.py` | FRED Terms of Use — 출처 표시. 원 자료는 미 연준 공개 데이터(public domain) | 결측 `"."` 제거, 영업일만 보유, 팩터는 **일별 차분(%p)** |
| `WTI` | WTI 유가 (USD/bbl) | FRED · 동일 | `DCOILWTICO` — 원 출처 U.S. EIA | `collectors/fred.py` | FRED Terms of Use — 출처 표시. 원 자료는 EIA 공개 데이터(public domain) | 결측 `"."` 제거, 영업일, 팩터는 **일별 변화율(%)** |
| `USDKRW` | 원/달러 환율 (매매기준율, KRW) | 한국은행 ECOS OpenAPI · `StatisticSearch` | 통계표 `731Y001` · 항목 `0000001` · 주기 D | `collectors/ecos.py` | 한국은행 ECOS 이용약관 — 출처 표시 (한국은행 경제통계시스템) | 빈 `DATA_VALUE` 제거, 영업일, **변화율(%)** |
| `KTB3Y` | 국고채 3년 금리 (%) | 한국은행 ECOS · 동일 | 통계표 `817Y002` · 항목 `010200000` · 주기 D | `collectors/ecos.py` | 동일 | 빈 값 제거, 영업일, **차분(%p)** |
| `BOK_BASE_RATE` (선택) | 한국은행 기준금리 (%) | 한국은행 ECOS · 동일 | 통계표 `722Y001` · 항목 `0101000` · 주기 D | `collectors/ecos.py` | 동일 | 팩터 카탈로그에 없음. 이벤트 검증·화면 참고용. 실패해도 경고만 |
| `KOSPI` | KOSPI 지수 | 공공데이터포털 · 금융위원회 **지수시세정보** `getStockMarketIndex` (원천 KRX) | `idxNm="코스피"`, 종가 `clpr` | `collectors/krx_prices.py` | 공공데이터포털 이용허락범위 (API 별 확인) — 출처 표시 (금융위원회·공공데이터포털) | `basDt`(YYYYMMDD) 파싱, 영업일, **변화율(%)** |
| `KOSPI_IT` | KOSPI 전기전자 업종지수 | 동일 | `idxNm="코스피 전기전자"` (명칭 확인 필요) | `collectors/krx_prices.py` | 동일 | 동일 |
| `KR_K200` | KOSPI 200 지수 | 동일 | `idxNm="코스피 200"` | `collectors/krx_prices.py` | 동일 | 동일 (자산 가격 시계열) |
| `US_EQ` | 미국 주식 대리 — TIGER 미국S&P500 ETF 종가 (KRW) | 공공데이터포털 · 금융위원회 **증권상품시세정보** `getETFPriceInfo` | 단축코드 `360750` | `collectors/krx_prices.py` | 동일 | ETF 원화 종가(환헤지 없음 → 환율 효과 포함), **변화율(%)** |
| `US_TECH` | 미국 기술주 대리 — TIGER 미국나스닥100 ETF 종가 (KRW) | 동일 | 단축코드 `133690` | `collectors/krx_prices.py` | 동일 | 동일 |
| `KR_SEMI` | 국내 반도체 — KODEX 반도체 ETF 종가 (KRW) | 동일 | 단축코드 `091160` | `collectors/krx_prices.py` | 동일 | 동일 |
| `KR_AUTO` | 국내 자동차 — KODEX 자동차 ETF 종가 (KRW) | 동일 | 단축코드 `091180` | `collectors/krx_prices.py` | 동일 | 동일 |

**팩터 변환 규칙** (`backend/app/engine/catalog.py`): 단위가 `%` 인 팩터(USDKRW, KOSPI, KOSPI_IT, US_EQ, WTI)는 일별 변화율 × 100, 단위가 `%p` 인 금리 팩터(DGS10, KTB3Y)는 일별 차분. 영업일이 다른 시장(한국·미국)은 두 시계열이 모두 있는 날짜만 회귀에 쓴다(내부 조인). 결측은 보간하지 않고 제외한다.

**수집하지 않는 것 — 제3자 저작권 지수**: S&P 500, 나스닥 100, 다우 등 지수 제공사(S&P Dow Jones Indices, Nasdaq 등)에 저작권이 있는 시리즈는 FRED 등에서 받을 수 있어도 **수집하지 않는다**. 해외 주식 노출은 위 표처럼 **국내 상장 해외지수 ETF 의 원화 종가**로 대신한다. 한계: ETF 종가에는 환율 변동과 추적 오차가 포함된다. 보고서에서는 "S&P 500" 이 아니라 "국내 상장 S&P 500 ETF (대리 변수)" 로 표기한다.

## 2. 정책 이벤트 (policy_event)

| 수집기 | 대상 | 출처 · API | 필터 | 라이선스 / 이용 조건 | 비고 |
| --- | --- | --- | --- | --- | --- |
| `collectors/federal_register.py` | 미국 관세·수입규제 고시 (`country=US`, `type=tariff\|regulation`) | Federal Register API `documents.json` (키 불필요) | 검색어 tariff / duties / "Section 232" / "Section 301" / "import restriction"; 기관 USTR·Commerce·ITA; 문서유형 PRESDOCU·RULE | **Public domain (U.S. Government work)**. 단 **관보(Federal Register) 로고·인장(seal) 사용 금지**, 출처·문서번호 표기 | `event_id="fr_"+document_number`, `summary=abstract`, `raw_text=abstract+본문 링크`, `value`=초록의 "N percent"/"N%" 정규식 |
| `collectors/korea_briefing.py` | 한국 정부 보도자료 (`country=KR`, `type=tariff\|rate\|regulation`) | 공공데이터포털 「문화체육관광부_대한민국 정책브리핑 보도자료」 API (키 있을 때) / korea.kr RSS (폴백) | 부처: 기획재정부·재정경제부·기획예산처·산업통상자원부·산업통상부·금융위원회·한국은행·관세청; 키워드: 관세·수출통제·기준금리·규제 | **공공누리 유형이 식별되는 자료만 저장**하고 `license` 에 "공공누리 제N유형 (조건) — 출처: 부처 / 정책브리핑" 을 기록. 식별 불가 자료는 건너뜀 | `event_id="kr_"+sha1(원문 URL)[:16]` |
| `data/demo_events.json` (seed) | 시연용 예시 이벤트 (`is_demo=true`) 와 실제 과거 발표 요약 | 수작업 | — | 시연용 예시(가상) / 공개 발표 내용 요약 | 화면에 '예시' 표시 |

공공누리 유형별 조건: 제1유형 출처표시 · 제2유형 출처표시+상업적 이용금지 · 제3유형 출처표시+변경금지 · 제4유형 출처표시+상업적 이용금지+변경금지. RIPPLE 은 보도자료 본문을 요약·인용만 하고 변경하지 않으며, 제2·4유형 자료는 비상업적 연구·시연 용도에만 쓴다.

## 3. 합성 데이터 (SYNTHETIC) 폴백

- 수집기를 아직 돌리지 않은 환경에서도 앱 흐름을 시연할 수 있도록 `python -m app.seed --synthetic` 이 `backend/app/synthetic.py` 로 **합성 시계열**을 만든다. 이 시리즈의 `series.source` 는 `"SYNTHETIC"`, `license` 는 "합성 데이터 — 실제 시장 데이터가 아님" 이며 화면 상단에 '합성 데이터' 배지가 표시된다.
- 합성 값은 변동성·상관계수를 실제와 비슷한 크기로 정했을 뿐 **실제 값이 아니다**. 제출물·보고서의 수치 근거로 쓰지 않는다.
- 실제 수집기가 같은 `series_id` 를 쓰면 `collectors/base.py: upsert_series()` 가 **합성 행을 모두 지우고** 실제 값만 남긴 뒤 `source`/`license` 를 실제 출처로 바꾼다 (합성·실제 값이 한 시리즈에 섞이지 않게). 반대로 `seed.py` 는 실제 출처 시리즈를 합성 값으로 덮어쓰지 않는다 (`--force` 제외).

## 4. 실행·키 설정

```bash
# .env 에 키 추가 (없는 키의 수집기는 건너뛴다)
FRED_API_KEY=...          # https://fred.stlouisfed.org/docs/api/api_key.html
ECOS_API_KEY=...          # https://ecos.bok.or.kr/api/  (인증키 신청)
DATA_GO_KR_API_KEY=...    # 공공데이터포털에서 금융위원회 지수시세정보·증권상품시세정보, 정책브리핑 보도자료 API 활용신청

cd <repo>
PYTHONPATH=backend:. python -m collectors.run_all --list                 # 수집기·필요 키 확인
PYTHONPATH=backend:. python -m collectors.run_all --only fred             # 수집기별 스모크 테스트
PYTHONPATH=backend:. python -m collectors.run_all --since 2015-01-01      # 전체 (하루 1회)
PYTHONPATH=backend:. python -m collectors.run_all --strict                # cron 용: API·네트워크 오류도 종료 코드 1
PYTHONPATH=backend:. python -m pytest collectors/tests -q                 # 파서·적재 테스트 (네트워크 불필요)
```

## 5. 확인 필요 (실제 API 로 스모크 테스트 시 점검)

| 항목 | 위치 | 내용 |
| --- | --- | --- |
| ECOS 통계표·항목 코드 | `collectors/ecos.py` `SERIES` | `731Y001/0000001`, `817Y002/010200000`, `722Y001/0101000` 을 ECOS 「통계코드검색」에서 확인. 일별(D) 주기 제공 여부 포함 |
| KRX 지수명 | `collectors/krx_prices.py` `SERIES` | `idxNm` 정확 일치 값 "코스피", "코스피 200", 특히 업종지수 "코스피 전기전자" (KRX 업종 개편 시 명칭 변경 가능). 첫 실행 로그의 "일치하는 행이 없음" 경고 확인 |
| 지수시세정보 API 의 업종지수 포함 여부 | 동일 | `getStockMarketIndex` 가 업종지수를 돌려주지 않으면 KOSPI_IT 대체 소스 필요 (예: KODEX 반도체 ETF 를 IT 업종 대리로) |
| ETF 단축코드 | 동일 | 360750 / 133690 / 091160 / 091180 (상품명 변경·합병 시 교체). 종가 필드 `clpr`, 날짜 `basDt` |
| data.go.kr 이용허락범위 | `krx_prices.LICENSE` | 활용신청 화면의 각 API 이용허락범위(공공누리 유형 또는 '제한 없음')로 문구 수정 |
| 정책브리핑 API 응답 태그 | `collectors/korea_briefing.py` `parse_press_release_xml` | `NewsItem / Title / SubTitle1 / DataContents / MinisterCode / OriginalUrl / ApproveDate` 태그명과 `startDate/endDate` 파라미터, 공공누리 정보가 별도 필드로 오는지 |
| 정책브리핑 RSS | 동일 `parse_rss` | 부처가 `author`/`dc:creator`/제목 접두사 중 어디에 오는지; 기사 페이지에 공공누리 유형 텍스트가 있는지 |
| Federal Register `fields[]` | `collectors/federal_register.py` `FIELDS` | `body_html_url`, `subtype` 이 fields 로 요청 가능한지 (불가하면 기본 필드로 폴백) |
| 정부조직 개편 부처명 | `korea_briefing.MINISTRIES` | 재정경제부·기획예산처·산업통상부 등 신 명칭 반영 여부 |

## 6. 출처 표기 예시 (제출물·보고서용)

```
[데이터 출처 및 이용 조건]
- 미국 국채 10년 금리(DGS10), WTI 유가(DCOILWTICO): FRED, Federal Reserve Bank of St. Louis (원 자료: Board of Governors of the Federal Reserve System; U.S. Energy Information Administration). FRED Terms of Use 에 따라 이용. 수집일 YYYY-MM-DD.
- 원/달러 환율(731Y001), 국고채 3년 금리(817Y002), 기준금리(722Y001): 한국은행 경제통계시스템(ECOS) OpenAPI. 출처 표시 조건에 따라 이용. 수집일 YYYY-MM-DD.
- KOSPI·KOSPI 200·KOSPI 전기전자 지수, 국내 상장 ETF 종가(TIGER 미국S&P500, TIGER 미국나스닥100, KODEX 반도체, KODEX 자동차): 공공데이터포털 금융위원회 지수시세정보·증권상품시세정보 API (원천: 한국거래소). 각 API 의 이용허락범위에 따라 이용, 출처 표시. 수집일 YYYY-MM-DD.
- 미국 관세·수입규제 고시: Federal Register (federalregister.gov) API, 문서번호 기재. 미국 연방정부 저작물(public domain). 관보 로고·인장은 사용하지 않음.
- 한국 정부 보도자료: 대한민국 정책브리핑(korea.kr), 각 자료의 공공누리 유형(제1~4유형) 및 발표 부처를 표기. 예: "기획재정부 보도자료 (대한민국 정책브리핑, 공공누리 제1유형)".
- 해외 주가지수(S&P 500 등)는 제3자 저작권 자료이므로 수집하지 않았으며, 국내 상장 해외지수 ETF 종가를 대리 변수로 사용함.
- 전처리: 결측값(".", 빈 값) 제거, 영업일 기준(두 시장 공통 영업일만 회귀에 사용), 가격·환율·유가는 일별 변화율(%), 금리는 일별 차분(%p). 보간하지 않음.
- 시연 모드에서 사용한 합성 시계열(source=SYNTHETIC)은 실제 시장 데이터가 아니며 보고서 수치의 근거로 쓰지 않음.
```

각 수치의 수집일은 DB `series_value.collected_at` / `policy_event.collected_at` 에서 가져와 화면의 계산 근거 패널과 보고서 부록에 자동으로 넣는다.
