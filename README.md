# RIPPLE — 정책 파급 스트레스 테스트 Agent

정책 발표(관세·금리·규제)나 직접 입력한 시나리오가 포트폴리오에 미치는 영향을 **파급 경로 → 충격 시나리오 → 손익 → 헤지 제안 → 보고서**로 만드는 AI Agent. 숫자는 격리된 Risk Engine만 계산하고, 화면의 모든 수치는 클릭하면 계산 근거(수식·입력값·출처·수집일·계산 ID)가 열린다.

국부펀드 KIC, AI 에이전트 공모전 출품작. 요건 정리: [`docs/COMPETITION.md`](docs/COMPETITION.md)

## 빠른 실행

```bash
# 1) 전체 스택 (PostgreSQL + API + 프론트엔드 빌드 + 수집기)
cp .env.example .env          # 키가 비어 있어도 동작: LLM offline 모드 + 합성 시계열(화면에 배지 표시)
docker compose up --build     # → http://localhost:8000

# 2) 개발 모드
cd backend && pip install -r requirements.txt && python -m app.seed --synthetic && uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev        # → http://localhost:5173 (/api 프록시)
```

`.env`에 `ANTHROPIC_API_KEY`를 넣으면 Agent가 Claude를 호출한다. `FRED_API_KEY`, `ECOS_API_KEY`, `DATA_GO_KR_API_KEY`를 넣고 `PYTHONPATH=backend:. python -m collectors.run_all --since 2015-01-01`을 실행하면 합성 시계열이 실제 데이터로 바뀐다.

## 동작 방식

```
정책 이벤트 ─▶ Event Analyst ─▶ Impact Mapper ─▶ Scenario Builder ─▶ Regime Finder ─▶ Risk Engine ─▶ Validator ─▶ Report Writer
  (수집기)      원문 구조화        경로 ≤3개·4단계      팩터 충격값          유사 국면 5개      β·손익·범위        규칙 4개       {{키}} 치환
                                     ▲                                                             │ 반려(≤2회)
                                     └─────────────────────────────────────────────────────────────┘
시나리오 직접 입력은 Scenario Builder부터, 충격값 수정은 Regime Finder부터 다시 실행한다.
```

- **신뢰성**: LLM 출력은 JSON 스키마 검증 후에만 반영. 보고서 수치는 계산 로그 키 자리표시자만 허용하고 엔진이 치환, 마커 밖 숫자는 Validator가 제거. 과거 재현 시 결정일 이후 데이터 차단.
- **두 가지 추정**: 팩터 모델(OLS β, 표준오차 범위) + 과거 유사 국면(표준화 코사인 유사도 상위 5구간의 실제 손익).
- **실행 과정 노출**: 단계별 입력·출력·소요·모델·토큰·반려를 `agent_step`에 기록, SSE로 실시간 타임라인.

## 주요 기능 (2026-10 기준)

- **수집 → 자동 사전분석**: 매일 09:00 KST 수집(FRED·ECOS·금융위 시세·Federal Register·정책브리핑) 직후, 관련성 높은 신규 이벤트를 Agent가 먼저 분석해 대시보드 카드에 예상 손익을 붙인다.
- **사후 검증**: 발표일이 지난 이벤트 분석은 발표 전 종가 기준 실제 20영업일 움직임과 비교해 방향 적중·오차를 결과 탭·보고서·`/backtest` 화면에 그대로 보여준다.
- **포트폴리오 비교**: 같은 충격값을 모든 모델 포트폴리오에 적용한 손익을 함께 계산한다 (엔진만, LLM 비용 없음).
- **데이터 관리**: 시계열 24종의 출처·수집일·라이선스·신선도·커버리지, 수집기 결과, 수집 실행을 한 화면(`/data`)에서 본다.
- **자체 검증**: `scripts/e2e_local.sh` 가 서버 기동 → 실제 Claude 분석 3건 → 화면 캡처 → 콘솔 오류 집계를 한 번에 돌린다.

## 저장소 구조

```
backend/     FastAPI + LangGraph · app/agents(7) · app/engine(계산) · app/api · tests(28)
frontend/    Vue 3 + Vite + TS · Pinia · Tailwind · ECharts · Vue Flow (화면 S1~S6)
collectors/  FRED · ECOS · 금융위 시세 · Federal Register · 정책브리핑 수집기 (하루 1회)
data/        가상 포트폴리오, 초기 이벤트, 유사 국면 라벨, SOURCES.md(출처·라이선스·전처리)
scripts/     backtest.py — 과거 사례 재현 검증 (시점 필터)
docs/        DESIGN.md(설계서) · API_CONTRACT.md · COMPETITION.md · DEPLOY.md · THIRD_PARTY.md
             design/(UI 핸드오프) · submission/(기획서·발표·시연 원고)
docker-compose.yml
```

## 문서

| 문서 | 내용 |
| --- | --- |
| [설계서](docs/DESIGN.md) | 아키텍처, Agent 명세, 계산 로직, 데이터 모델, API, 화면, 개발 순서 |
| [API 규약](docs/API_CONTRACT.md) | 응답 형태, SSE 이벤트, 계산 근거 키 |
| [UI 핸드오프](docs/design/README.md) | 화면 S1~S6 시각 스펙, 토큰 |
| [데이터 출처](data/SOURCES.md) | 시리즈별 출처·수집일·라이선스·전처리 |
| [외부 자원](docs/THIRD_PARTY.md) | 모델·라이브러리·폰트 |
| [배포](docs/DEPLOY.md) | 데모 URL 구성 |
| [기획서 원고](docs/submission/PROPOSAL.md) · [발표 원고](docs/submission/PRESENTATION.md) · [시연 대본](docs/submission/DEMO_SCRIPT.md) | 제출물 |

## 테스트

```bash
cd backend && python -m pytest tests -q                       # 엔진·Agent·Validator·API·SSE
cd frontend && npm run build && npx vitest run                 # 타입 검사·빌드·서식 유틸
PYTHONPATH=backend:. python -m pytest collectors/tests -q      # 수집기 파서
PYTHONPATH=backend python scripts/backtest.py                  # 과거 사례 재현 (실데이터 필요)
```

## 데이터·라이선스 원칙

공개 API만 사용하고 모든 시리즈에 출처·수집일·라이선스를 기록해 화면과 보고서에 자동 표기한다. 제3자 저작권이 걸린 해외 주가지수(S&P 500 등)는 수집하지 않고 국내 상장 ETF 시세로 대체한다. 포트폴리오는 가상 모델 포트폴리오이며 실제 기관 보유내역이 아니다. 자세한 내용은 [`data/SOURCES.md`](data/SOURCES.md).
