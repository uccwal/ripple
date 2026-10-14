# RIPPLE Backend

FastAPI + LangGraph. Agent 7개가 공유 상태(RunState)를 순서대로 채우고, 숫자 계산은 `app/engine`만 한다.

## 실행

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env          # 키가 없어도 동작 (offline 모드 + 합성 시계열)
python -m app.seed --synthetic      # 테이블 생성 + 가상 포트폴리오 + 초기 이벤트 + 합성 시계열
uvicorn app.main:app --reload --port 8000
# http://localhost:8000/docs
```

테스트: `python -m pytest tests -q` (28개, 약 6초. 그래프 실행과 SSE까지 포함)

## 구조

```
app/
├─ main.py            FastAPI 앱 · frontend/dist 가 있으면 함께 서빙
├─ config.py          .env 설정 (모델, 재시도 상한, 헤지 기준값)
├─ db.py              SQLAlchemy (SQLite 기본, PostgreSQL 지원)
├─ seed.py            초기 데이터 적재
├─ synthetic.py       데모용 합성 시계열 (source=SYNTHETIC, 화면에 배지 표시)
├─ llm.py             Claude 구조화 출력 호출 · offline 모드
├─ runner.py          단계 로그(agent_step) · SSE 이벤트 버스 · 타임라인 조립
├─ graph.py           LangGraph 상태 그래프 (라우팅, 반려 루프, 재계산 진입)
├─ api/routes.py      REST + SSE (docs/API_CONTRACT.md)
├─ api/report_html.py 보고서 인쇄용 HTML
├─ agents/            event_analyst · impact_mapper · scenario_builder · validator · report_writer
├─ engine/            catalog(팩터) · data · factors(OLS) · regimes(유사 국면) · risk(손익·계산 로그) · hedge · fmt
├─ models/            tables.py (테이블 9개) · state.py (RunState, LLM 출력 스키마)
└─ prompts/           Agent별 프롬프트
```

## 실행 흐름

```
POST /api/runs ─▶ Run(queued) ─▶ 스레드에서 graph.execute()
   event 입구:    Event Analyst → Impact Mapper → Scenario Builder → Regime Finder → Risk Engine → Validator → Report Writer
   scenario 입구: Scenario Builder 부터 (앞 2단계 skip)
   PATCH /scenario: Regime Finder 부터 (앞 3단계 '이전 결과 재사용')
   Validator 반려 → Impact Mapper(≤2회) / Risk Engine(≤1회) 재실행. 상한 초과 시 partial + 경고
단계마다 agent_step 기록 → SSE step_started/step_finished/step_retry/run_finished
```

## 신뢰성 장치

| 장치 | 위치 |
| --- | --- |
| LLM 출력은 JSON 스키마(Pydantic) 검증 후에만 상태 반영 | `llm.structured`, `models/state.py` |
| 숫자는 엔진만 계산, LLM은 `{{키}}` 자리표시자만 사용 → 엔진이 치환 | `agents/report_writer.py` |
| 보고서의 마커 밖 숫자는 Validator R4가 찾아 문장 제거 + 경고 | `agents/validator.check_report`, `graph._drop_uncited` |
| 모든 수치 → 계산 근거(수식·입력값·출처·수집일·코드 해시) | `engine/risk._entries`, `GET /runs/{id}/calc-log` |
| 과거 재현 시 결정일 이후 데이터 차단 | `engine/data.load_levels(as_of)` |
| 헤지 제안은 규칙 결과만 | `engine/hedge.py` |

## LLM 모드

| 조건 | 동작 |
| --- | --- |
| `ANTHROPIC_API_KEY` 설정 | Claude 호출 (`MODEL_DEFAULT`, Impact Mapper는 `MODEL_IMPACT_MAPPER`) |
| 키 없음 또는 `LLM_MODE=offline` | 규칙 기반 대체 (유형별 표준 경로, 자연어 파서, 템플릿 문장). 계산·검증·보고서 구조는 동일 |

응답 거부(`stop_reason=refusal`)·토큰 한도·스키마 실패는 단계 실패로 기록하고 실행을 `failed`로 끝낸다.
