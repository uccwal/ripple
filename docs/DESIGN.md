# RIPPLE 시스템 설계서

2026-10-14 · uccwal

정책 파급 스트레스 테스트 Agent RIPPLE의 구현 설계입니다. 화면 정의서(6장)는 디자인 작업에 바로 넘길 수 있도록 작성했습니다. 디자인 핸드오프는 [`docs/design/`](design/README.md)에 있습니다.

## 1. 시스템 아키텍처

프론트엔드 → API → LangGraph Orchestrator → 저장소·LLM의 4계층이며, **계산은 격리된 Python 실행 환경의 Risk Engine만 담당**합니다.

수집기는 하루 1회 배치로 시계열과 정책 발표를 적재하고, LLM Agents는 외부 LLM API를 호출하되 숫자는 Risk Engine 결과만 인용합니다.

## 2. Agent 상세 명세

모든 Agent는 LangGraph의 **공유 상태(RunState)** 를 읽고 자기 필드만 씁니다. LLM 호출 결과는 JSON 스키마로 검증한 뒤에만 상태에 반영합니다.

**공유 상태 RunState**

```json
{
  "run_id": "uuid",
  "entry": "event | scenario",
  "event": {"id": "", "country": "US", "type": "tariff", "targets": ["semiconductor"], "value": 0.25, "announced_at": "2026-10-01", "source_url": ""},
  "impact_paths": [{"steps": [{"from": "", "to": "", "direction": "+|-", "confidence": "high|mid|low", "evidence": [""]}]}],
  "scenario": {"shocks": [{"variable": "USDKRW", "change": 0.05, "unit": "pct", "basis": ""}], "horizon_days": 20},
  "regimes": [{"start": "", "end": "", "similarity": 0.0}],
  "result": {"portfolio_pnl": 0.0, "by_asset": [], "top_contributors": [], "calc_log_id": ""},
  "validation": {"passed": false, "issues": []},
  "report": {"markdown": "", "citations": []},
  "retries": {"impact": 0, "risk": 0}
}
```

**Agent별 명세**

| Agent | 입력 | 출력 | 도구 | 실패 처리 |
| --- | --- | --- | --- | --- |
| Orchestrator | 사용자 입력 | `entry`, 실행 계획 | LangGraph 라우팅 | 재시도 한도 초과 시 부분 결과 + 경고로 종료 |
| Event Analyst | 정책 발표 원문 | `event` | 발표 수집기, LLM 구조화 | 필수 필드 누락 시 사용자 확인 요청 |
| Impact Mapper | `event` | `impact_paths` (최대 3개 경로, 경로당 최대 4단계) | 무역통계·ECOS 조회, LLM 추론 | 근거 없는 단계는 `low`로 표시, Validator 반려 시 재추론 (최대 2회) |
| Scenario Builder | `impact_paths` 또는 자연어 시나리오 | `scenario` | 과거 변동성 통계 조회 | 충격값이 과거 최대 변동폭을 넘으면 경고 표시 |
| Regime Finder | `scenario` | `regimes` (상위 5개) | 시계열 유사도 계산 (Python) | 유사 구간이 없으면 팩터 모델만 사용 |
| Risk Engine | `scenario`, 포트폴리오, `regimes` | `result` + 계산 로그 | 격리된 Python 실행 | 계산 오류 시 1회 재실행 후 실패 보고 |
| Validator | `result`, `impact_paths`, 보고서 초안 | `validation` | 규칙 검사, 계산 로그 대조 | 실패 항목별로 담당 Agent에 반려 |
| Report Writer | 전체 상태 | `report` | 템플릿, 차트 데이터 생성 | 수치는 `result`에서만 인용, 직접 생성 금지 |

**실행 흐름 규칙**

- `entry = event`: Event Analyst → Impact Mapper → Scenario Builder → Regime Finder → Risk Engine → Validator → Report Writer
- `entry = scenario`: Scenario Builder부터 시작
- 사용자가 화면에서 충격값을 수정하면 Regime Finder부터 다시 실행합니다.
- 모든 단계의 입력·출력·소요 시간을 `agent_steps` 테이블에 남겨 화면의 "실행 과정" 패널에 보여줍니다.

**LLM 모델 전략**

| 구간 | 모델 | 설정 |
| --- | --- | --- |
| 개발·예선 기간 | 전 단계 Claude Haiku 5.5 | `MODEL_DEFAULT=claude-haiku-5-5` |
| 본선 튜닝 | Impact Mapper만 Claude Sonnet 5.5, 나머지 Haiku 5.5 | `MODEL_IMPACT_MAPPER=claude-sonnet-5-5` |

- 재시도 상한: Impact Mapper 2회, Risk Engine 1회. 상한을 넘으면 부분 결과와 경고로 종료합니다.
- 프롬프트에는 시계열 원본 대신 요약 통계만 넣습니다 (Haiku 5.5는 프롬프트 10만 토큰 초과 시 단가가 오름).
- 데모 시나리오 결과는 캐시해 심사 기간 비용과 장애를 막습니다.

## 3. 계산 로직

Risk Engine은 **팩터 모델 추정치**와 **과거 유사 국면 추정치** 두 가지를 함께 계산해, 하나의 숫자에 의존하지 않게 합니다.

**① 팩터 민감도 추정** — 자산 i의 일별 수익률을 팩터 수익률에 회귀합니다 (최근 3~5년).

$$r_{i,t} = \alpha_i + \sum_{k} \beta_{i,k} f_{k,t} + \varepsilon_{i,t}$$

팩터 후보: 원/달러 환율, 한국 국고채 3년, 미국 국채 10년, WTI 유가, KOSPI, 업종 지수, 국내 상장 해외지수 ETF(해외 주식 노출의 대리 변수). 제3자 저작권이 걸린 해외 주가지수 시리즈는 사용하지 않습니다.

**② 시나리오 충격 적용** — 충격값 Δf_k를 넣어 자산별 영향과 포트폴리오 손익을 구합니다.

$$\Delta R_i = \sum_{k} \beta_{i,k} \, \Delta f_k, \qquad \Delta P = \sum_{i} w_i \, \Delta R_i$$

- 손실 기여도 = w_i × ΔR_i, 절댓값 기준 상위 5개를 "손실 기여 상위 노출"로 표시합니다.
- 베타의 표준오차로 추정 범위(하한~상한)를 함께 계산합니다.

**③ 과거 유사 국면** — 시나리오 충격 벡터와 과거 구간의 실제 변화 벡터를 비교합니다.

- 과거 데이터를 `horizon_days`(기본 20영업일) 단위로 잘라 팩터별 변화율 벡터를 만들고, 표준화합니다.
- 시나리오 벡터와의 코사인 유사도 상위 5개 구간을 고릅니다.
- 각 구간에서 포트폴리오에 실제로 일어났을 손익을 재계산해, 팩터 모델 추정치와 나란히 보여줍니다.

**④ 헤지 제안 규칙**

| 조건 | 제안 |
| --- | --- |
| 환율 팩터 기여가 손실의 30% 이상 | 해당 통화 노출 환헤지 비율 상향 |
| 단일 업종 기여가 손실의 40% 이상 | 업종 비중 축소 또는 반대 방향 업종으로 분산 |
| 금리 팩터 기여가 큰 경우 | 채권 듀레이션 조정 |

규칙의 기준값(30%, 40%)은 MVP 기본값이며 설정에서 바꿀 수 있습니다. 헤지 제안 문장은 규칙 결과로만 만들고, LLM은 설명 문장만 다듬습니다.

## 4. 데이터 모델

PostgreSQL 하나에 시계열, 정책 이벤트, 포트폴리오, 실행 이력을 저장합니다. 테이블은 9개입니다.

| 테이블 | 주요 컬럼 | 설명 |
| --- | --- | --- |
| `series` | series_id (PK), name, source, unit, frequency, license | 시계열 메타 (예: USDKRW, DGS10) |
| `series_value` | series_id (FK), date, value, collected_at | 일별 값, (series_id, date) 유니크 |
| `policy_event` | event_id (PK), country, type, title, targets (jsonb), value, announced_at, source_url, raw_text | 수집·구조화된 정책 발표 |
| `portfolio` | portfolio_id (PK), name, base_currency, description | 가상 모델 포트폴리오 |
| `holding` | portfolio_id (FK), asset_id, weight, currency, sector | 보유 비중 |
| `factor_beta` | asset_id, factor_id, beta, std_err, r2, window_start, window_end | 팩터 민감도 추정 결과 |
| `run` | run_id (PK), entry, input_text, event_id, portfolio_id, status, created_at | Agent 실행 1회 |
| `agent_step` | step_id (PK), run_id (FK), agent, input (jsonb), output (jsonb), started_at, ended_at, status | 단계별 실행 로그 (화면의 실행 과정) |
| `calc_log` | calc_id (PK), run_id (FK), code_hash, inputs (jsonb), outputs (jsonb) | Risk Engine 계산 기록, 보고서 수치의 근거 |

**설계 원칙**

- 수집한 모든 값에 `collected_at`과 출처를 남겨, 제출물의 출처·수집일 기재에 그대로 씁니다.
- 보고서의 모든 수치는 `calc_log.outputs`의 키를 참조합니다. Validator는 이 참조가 없는 수치를 반려합니다.

**데이터 소스와 라이선스 원칙**

| 수집기 | 데이터 | 출처 | 사용 원칙 |
| --- | --- | --- | --- |
| `federal_register.py` | 미국 관보 (관세·규제 고시) | Federal Register API | API 키 불필요. 관보 로고·인장 사용 금지 |
| `korea_briefing.py` | 한국 정부 보도자료 | 대한민국 정책브리핑 | 공공누리 유형이 표시된 자료만 수집, 유형별 출처 표시 |
| `fred.py` | 미 국채 10년(DGS10), WTI(DCOILWTICO), 달러지수(DTWEXBGS) | FRED API | 제3자 저작권이 표시된 시리즈(S&P 500 등 주가지수)는 수집하지 않음 |
| `ecos.py` | 국고채 금리, 원/달러 환율, 기준금리, 수출입 | 한국은행 ECOS API | 출처 표시 |
| `krx_prices.py` | 국내 주식·지수, 국내 상장 해외지수 ETF 시세 | 공공데이터포털 금융위원회 시세정보·증권상품시세정보 API | 이용허락범위를 확인한 API만 사용. 해외 주식 노출은 해외지수 ETF로 대체 |
| (확장) | 품목별 수출입 실적 | 공공데이터포털 관세청 수출입 통계 API | 위와 동일 |

수집한 모든 시리즈는 `series.license`에 이용 조건을 남기고, `data/SOURCES.md`와 기획서 부록에 같은 내용을 기재합니다.

## 5. API 명세

FastAPI REST API이며, Agent 실행 진행 상황은 **SSE(Server-Sent Events)** 로 화면에 실시간 전달합니다.

| 메서드 | 경로 | 설명 | 주요 응답 |
| --- | --- | --- | --- |
| GET | `/api/events` | 정책 이벤트 목록 (필터: country, type, 기간) | 이벤트 배열 |
| GET | `/api/events/{id}` | 이벤트 상세 (원문, 구조화 결과) | `policy_event` |
| GET | `/api/portfolios` | 포트폴리오 목록 | 배열 |
| GET | `/api/portfolios/{id}` | 보유 비중, 업종·통화 구성 | 보유 배열 |
| POST | `/api/runs` | 실행 시작. body: `{entry, event_id?, scenario_text?, portfolio_id}` | `run_id` |
| GET | `/api/runs/{id}/stream` | 실행 진행 SSE (단계 시작·종료·결과) | 이벤트 스트림 |
| GET | `/api/runs/{id}` | 실행 결과 전체 (경로, 시나리오, 결과, 검증, 보고서) | RunState |
| PATCH | `/api/runs/{id}/scenario` | 충격값 수정 후 재계산 (Regime Finder부터) | 새 `run_id` |
| GET | `/api/runs/{id}/calc-log` | 계산 근거 (입력, 코드 해시, 출력) | `calc_log` |
| GET | `/api/runs/{id}/report` | 보고서 (Markdown, PDF 다운로드) | 파일 |
| GET | `/api/series/{id}` | 시계열 조회 (차트용) | 날짜·값 배열 |
| GET | `/api/runs` | 실행 이력 목록 | 배열 |

## 6. 화면 정의서 (디자인 전달용)

화면은 6개이며, 핵심은 **분석 워크스페이스(S3)** 하나에 실행 과정·경로·시나리오·결과·보고서를 탭으로 모으는 구조입니다. 상세 시각 스펙은 [`docs/design/README.md`](design/README.md)를 따릅니다.

**디자인 원칙**

- **숫자는 모두 근거로 이어진다**: 화면의 모든 수치를 클릭하면 계산 근거(S5)가 열립니다. 심사 항목 "결과의 신뢰성"을 화면으로 보여주는 장치입니다.
- **Agent가 일하는 모습이 보인다**: 실행 중 단계별 진행 상황을 실시간으로 보여줍니다. "Agent 기술성"을 시연하는 장치입니다.
- **톤**: 금융 업무 도구답게 차분하고 정보 밀도가 높은 대시보드. 손익 색상은 국내식으로 통일 (이익·상승 빨강, 손실·하락 파랑).
- **해상도**: 데스크톱 1440px 기준, 1280px까지 대응. 모바일은 MVP 범위 밖.

**화면 목록**

| ID | 화면 | 목적 | 진입 |
| --- | --- | --- | --- |
| S1 | 이벤트 대시보드 | 최근 정책 이벤트 확인, 분석 시작 | 첫 화면 |
| S2 | 새 분석 | 입구 선택, 포트폴리오 선택, 시나리오 입력 | S1의 "분석하기" 또는 상단 "새 분석" |
| S3 | 분석 워크스페이스 | 실행 과정, 파급 경로, 시나리오, 결과, 보고서 | 실행 시작 직후 |
| S4 | 포트폴리오 | 가상 포트폴리오 구성 확인 | 상단 메뉴 |
| S5 | 계산 근거 (패널) | 수치의 입력값, 계산식, 데이터 출처 | 모든 수치 클릭 |
| S6 | 실행 이력 | 과거 분석 목록, 다시 열기 | 상단 메뉴 |

**S1 이벤트 대시보드**

- 상단 바: 서비스명, 메뉴(이벤트 / 포트폴리오 / 실행 이력), "새 분석" 버튼
- 필터: 국가, 유형(관세·금리·규제), 기간
- 이벤트 카드 목록: 국가 깃발 아이콘, 유형 태그, 제목, 발표일, 핵심 수치(예: 관세 25%), "분석하기" 버튼
- 우측 요약: 오늘 수집된 이벤트 수, 최근 분석 3건 바로가기

**S2 새 분석**

- 입구 선택 토글: "정책 이벤트로 시작" / "시나리오 직접 입력"
- 이벤트 선택 시: 선택된 이벤트 요약 카드
- 시나리오 입력 시: 자연어 입력창 + 예시 문구 칩 3개
- 포트폴리오 선택 드롭다운, 분석 기간(기본 20영업일)
- "분석 시작" 버튼

**S3 분석 워크스페이스**

- 좌측 패널 "실행 과정": Agent 단계 세로 타임라인 (대기 / 실행 중 / 완료 / 재시도 / 실패 상태), 단계별 소요 시간, 펼치면 입력·출력 요약. 재추론 루프는 되돌아가는 화살표로 표시
- 상단 요약 바: 포트폴리오 예상 손익(%·금액), 추정 범위, 검증 상태 배지(통과 / 경고)
- 탭 ① **파급 경로**: 노드-엣지 그래프 (정책 → 산업 → 거시 변수). 엣지에 방향(+/−)과 확신도(굵기·실선/점선). 노드 클릭 시 근거 목록
- 탭 ② **시나리오**: 변수별 충격값 표(변수, 충격값, 단위, 근거, 과거 최대 변동폭 대비 위치 막대). 값 직접 수정 + "재계산" 버튼
- 탭 ③ **결과**: 자산별 손익 막대 차트, 손실 기여 상위 5개 표, 팩터 모델 vs 과거 유사 국면 추정치 비교, 유사 국면 목록(기간, 유사도, 당시 실제 손익)
- 탭 ④ **보고서**: 문서형 보고서 미리보기(요약, 경로, 손익, 헤지 제안, 출처), PDF 다운로드 버튼

**S4 포트폴리오**

- 포트폴리오 선택, 자산군·통화·업종 구성 도넛 차트, 보유 비중 표
- "가상 포트폴리오" 표시 배지 상시 노출

**S5 계산 근거 패널** (우측 슬라이드 패널)

- 선택한 수치, 계산식, 입력값 표(팩터, 베타, 충격값), 데이터 출처와 수집일, 계산 ID

**S6 실행 이력**

- 표: 실행일시, 입구 유형, 이벤트·시나리오 요약, 포트폴리오, 예상 손익, 검증 상태, "열기"

**공통 상태**: 로딩(스켈레톤), 데이터 없음, 실행 실패(재시도 버튼), 근거 불충분 경고(노란 배지)

## 7. 프로젝트 구조와 개발 순서

저장소 하나에 백엔드·프론트엔드·데이터 수집을 함께 두고, Docker Compose로 한 번에 띄웁니다.

```
ripple/
├─ backend/
│  ├─ app/
│  │  ├─ api/            # FastAPI 라우터 (events, runs, portfolios, series)
│  │  ├─ agents/         # orchestrator, event_analyst, impact_mapper, scenario_builder,
│  │  │                  # regime_finder, risk_engine, validator, report_writer
│  │  ├─ graph.py        # LangGraph 상태 그래프 정의
│  │  ├─ engine/         # 팩터 회귀, 충격 적용, 유사 국면 탐색 (순수 계산 코드)
│  │  ├─ models/         # DB 모델, Pydantic 스키마 (RunState 등)
│  │  └─ prompts/        # Agent별 프롬프트
│  └─ tests/
├─ collectors/           # FRED, ECOS, 시세, Federal Register, 보도자료 수집기
├─ frontend/             # Vue 3 (S1~S6)
├─ data/                 # 가상 포트폴리오 정의, 출처·라이선스 목록
├─ docker-compose.yml
└─ README.md             # 실행 방법, 사용 기술, 데이터 출처
```

**개발 순서**

| 순서 | 작업 | 시기 | 완료 기준 |
| --- | --- | --- | --- |
| 1 | 수집기 + DB 적재 (FRED, ECOS, 시세) | 예선 기간 | 5년치 일별 시계열 적재 |
| 2 | Risk Engine (팩터 회귀, 충격 적용, 유사 국면) | 예선 평가 기간 | 직접 시나리오로 손익 계산 성공 |
| 3 | 정책 이벤트 수집 + Event Analyst | 예선 평가 기간 | 관세·금리·규제 이벤트 구조화 |
| 4 | Impact Mapper, Scenario Builder, Validator, Report Writer + LangGraph 연결 | 본선 1주차 | 이벤트 입력부터 보고서까지 흐름 완주 |
| 5 | 프론트엔드 S1~S6 + SSE 실행 과정 | 본선 2주차 | 데모 시나리오 3개 시연 가능 |
| 6 | 과거 사례 재현도 측정, 배포, README, 시연 영상 | 본선 3주차 | 데모 URL·GitHub·발표자료 제출 |

**데모 시나리오 (본선 시연용)**

1. 미국 반도체 관세 발표 → 국내 IT 업종·환율 경로 → 포트폴리오 손익
2. 미국 기준금리 인상 → 원/달러, 채권 → 손익과 듀레이션 헤지 제안
3. 직접 입력: "유가 30% 급등 + 원화 10% 약세" → 과거 유사 국면 비교

**과거 사례 재현 검증** (기획서 문제 정의의 실제 사례와 연결)

| 사례 | 기준 구간 | 검증 방법 |
| --- | --- | --- |
| 2019년 7월 일본 반도체·디스플레이 소재 수출규제 | 2019년 7월 발표 직후 20영업일 | 당시 공개 정보만으로 RIPPLE을 실행해 추정한 코스피·업종 영향과 실제 움직임(7/8 코스피 2.2% 하락 등)을 방향·크기로 비교 |
| 2025년 4월 미국 상호관세 (한국 25%) | 2025년 4월 3일 발표 직후 20영업일 | 원/달러 충격 추정치와 실제 움직임(4/9 1,484원까지 상승)을 비교 |

- 재현 실행 시 결정일 이후 데이터는 계산에 넣지 않습니다 (시점 필터).
- 결과는 기획서 기대 효과의 "과거 사례 재현도" 지표와 본선 발표 자료에 사용합니다.
