# API 규약 (백엔드 ↔ 프론트엔드)

설계서 5장 API 명세의 실제 응답 형태입니다. 백엔드는 FastAPI(`:8000`), 프론트엔드 개발 서버(`:5173`)는 `/api`를 백엔드로 프록시합니다.

## 공통 단위·표기

| 항목 | 단위 | 예 |
| --- | --- | --- |
| 손익·수익률 (`portfolio_pnl`, `ret`) | % | `-3.8` = −3.8% |
| 기여도 (`contribution`) | %p (포트폴리오 손익 기여) | `-1.12` |
| 충격값 `change` | `unit`이 `%`면 변화율(%), `%p`면 금리 변화(%p) | `5.0`, `-0.15` |
| 금액 (`pnl_amount`, `aum`) | 억 원 | `-1240` |
| 날짜 | `YYYY-MM-DD`, 일시는 ISO 8601 | |

화면 표기 규칙(유니코드 마이너스 `−`, 손익색, tabular-nums)은 프론트엔드가 적용합니다. 백엔드는 숫자만 보냅니다. 단, 계산 근거 패널(S5) 표의 셀은 백엔드가 서식을 적용한 문자열로 보냅니다.

## 팩터 (factor_id)

| factor_id | 이름 | unit |
| --- | --- | --- |
| `USDKRW` | 원/달러 환율 | % |
| `DXY_BROAD` | 달러 인덱스 (광의, 연준 산출 DTWEXBGS) | % |
| `KOSPI` | KOSPI | % |
| `KOSPI_IT` | KOSPI IT 업종 | % |
| `US_EQ` | 미국 주식 (국내 상장 S&P 500 ETF 대리) | % |
| `DGS10` | 미국 국채 10년 | %p |
| `DGS2` | 미국 국채 2년 | %p |
| `KTB3Y` | 국고채 3년 | %p |
| `WTI` | WTI 유가 | % |

## GET `/api/meta`

```json
{
  "service": "RIPPLE",
  "engine_version": "0.1.0",
  "llm_mode": "anthropic | offline",
  "model_default": "claude-haiku-5-5",
  "last_collected_at": "2026-10-14T09:00:00",
  "today_event_count": 3,
  "today_event_delta": 1,
  "events_by_source": [{"source": "Federal Register", "count": 2}],
  "synthetic_data": true
}
```

`synthetic_data`가 `true`면 시계열 일부가 데모용 합성 데이터입니다. 상단 바에 "합성 데이터" 경고 배지를 상시 노출합니다.

## GET `/api/events?country=US&type=tariff&days=30&relevance=mid&limit=200`

`country`: `US|KR|EU|CN` (생략 시 전체), `type`: `tariff|rate|regulation`, `days`: 7/30/90 (발표일 기준, 생략 시 전체), `relevance`: `high`(높음만) / `mid`(높음·중간; 미평가·예시 이벤트는 항상 포함), `limit` 기본 200.

수집된 외국어 이벤트는 수집 직후 Claude가 한국어 제목·요약·유형·수치·관련성(`relevance`: high/mid/low)으로 구조화하며 원문 제목은 `title_orig`에 남습니다 (offline 모드에서는 영어 그대로, `relevance`=null).

```json
[{
  "event_id": "ev_us_semis_tariff",
  "country": "US", "country_name": "미국",
  "type": "tariff", "type_name": "관세",
  "title": "반도체 수입품 관세 부과 발표",
  "summary": "…",
  "targets": ["semiconductor"],
  "value": 25.0, "value_text": "관세율 25%",
  "announced_at": "2026-10-01",
  "source": "Federal Register", "source_url": "https://…",
  "is_demo": false,
  "title_orig": "Adjusting Imports of Semiconductors …", "relevance": "high",
  "last_run": {"run_id": "…", "portfolio_pnl": -3.8}
}]
```

`last_run`은 분석 이력이 없으면 `null`. `is_demo`가 `true`면 시연용 예시 이벤트(카드에 "예시" 표시).

## GET `/api/events/{id}`

위 객체 + `raw_text`, `collected_at`.

## GET `/api/portfolios`

```json
[{"portfolio_id": "pf_a", "name": "가상 모델 포트폴리오 A", "base_currency": "USD", "description": "…", "aum": 32300, "holdings_count": 8}]
```

## GET `/api/portfolios/{id}`

```json
{
  "portfolio_id": "pf_a", "name": "…", "base_currency": "USD", "description": "…", "aum": 32300,
  "holdings": [{"asset_id": "KR_SEMI", "name": "국내 반도체 대형주", "asset_class": "주식", "currency": "KRW", "sector": "반도체", "weight": 14.0}]
}
```

`weight`는 % (합계 100).

## POST `/api/runs`

요청: `{"entry": "event" | "scenario", "event_id"?: "…", "scenario_text"?: "…", "portfolio_id": "pf_a", "horizon_days"?: 20}`
응답: `{"run_id": "…"}` — 실행은 백그라운드에서 진행됩니다.

## GET `/api/runs/{id}` — RunState

```json
{
  "run_id": "…", "parent_run_id": null,
  "entry": "event", "status": "queued | running | done | partial | failed",
  "error": null,
  "title": "미국 반도체 수입품 관세 25%",
  "input_text": "…",
  "portfolio": {"portfolio_id": "pf_a", "name": "가상 모델 포트폴리오 A", "aum": 32300},
  "horizon_days": 20, "as_of": "2026-10-14",
  "created_at": "…", "finished_at": "…", "elapsed_ms": 14000,
  "llm_mode": "anthropic | offline",
  "synthetic_data": true,

  "event": {"event_id": "…", "country": "US", "type": "tariff", "title": "…", "targets": ["semiconductor"], "value": 25.0, "value_text": "관세율 25%", "announced_at": "2026-10-01", "source": "Federal Register", "source_url": "…"},

  "impact_paths": [{
    "path_id": "p1", "excluded": false, "reason": null,
    "steps": [{"from": "n1", "to": "n2", "direction": "+|-", "confidence": "high|mid|low", "evidence": ["ev3"]}]
  }],
  "graph": {
    "nodes": [{"id": "n1", "label": "미국 반도체 관세 25%", "layer": "policy|industry|macro|asset", "confidence": "high|mid|low", "factor_id": null, "direction_text": "출발 이벤트", "evidence": [{"id": "ev1", "text": "…", "source": "…", "collected_at": "2026-10-01"}]}],
    "edges": [{"source": "n1", "target": "n2", "direction": "+|-", "confidence": "high|mid|low"}]
  },

  "scenario": {
    "horizon_days": 20,
    "shocks": [{"variable": "USDKRW", "name": "원/달러 환율", "change": 5.0, "unit": "%", "basis": "과거 유사 관세 국면 중앙값", "hist_max": 14.2, "hist_pct": 35.2, "over_hist": false}]
  },

  "regimes": [{"start": "2018-03-22", "end": "2018-04-19", "similarity": 0.87, "tag": "미·중 1차 관세", "pnl": -4.9, "factor_changes": {"USDKRW": 2.1}}],

  "result": {
    "portfolio_pnl": -3.8, "pnl_amount": -1240, "aum": 32300,
    "range": {"low": -5.1, "high": -2.6},
    "by_asset": [{"asset_id": "KR_SEMI", "name": "…", "weight": 14.0, "ret": -14.2, "contribution": -1.99, "currency": "KRW", "sector": "반도체", "asset_class": "주식"}],
    "top_contributors": ["KR_SEMI", "…"],
    "factor_contrib": [{"factor_id": "USDKRW", "name": "원/달러 환율", "beta": -0.31, "se": 0.04, "shock": 5.0, "unit": "%", "contribution": -1.55, "share": 41}],
    "regime_estimate": {"median": -4.9, "low": -6.2, "high": -1.9, "n": 5},
    "hedges": [{"rule_id": "fx", "title": "달러 노출 환헤지 비율 상향", "why": "환율 팩터가 손실의 41% 기여", "rule": "환율 팩터 기여 ≥ 손실의 30%", "key": "fc:USDKRW"}],
    "calc_log_id": "calc_…"
  },

  "validation": {"passed": true, "status": "pass | warn | fail", "rules_total": 4, "rules_passed": 4,
    "issues": [{"code": "low_evidence", "severity": "warn|error", "agent": "Impact Mapper", "message": "…"}]},

  "report": {"markdown": "…", "citations": [{"n": 1, "name": "FRED · DGS10", "collected_at": "2026-10-13", "url": "…"}]},

  "steps": [/* 아래 Step 객체 7개 */]
}
```

진행 중이거나 실패한 실행에서는 `event` 이후 필드가 `null`/빈 배열일 수 있습니다. 시나리오 입구에서는 `event`=null, `impact_paths`=[], `graph`=null.

### Step 객체 (타임라인 한 줄, Agent별 최신 시도 기준)

```json
{
  "idx": 0, "agent": "Event Analyst", "desc": "이벤트 구조화",
  "status": "wait | running | done | retry | failed | skip",
  "attempt": 1, "elapsed_ms": 1200,
  "note": "1차 반려(경로 2 근거 부족) 후 2차 통과",
  "input_summary": "…", "output_summary": "…",
  "model": "claude-haiku-5-5 | engine (LLM 없음) | 규칙 (LLM 없음) | offline 규칙",
  "tokens": "3,120 / 412"
}
```

순서: 0 Event Analyst, 1 Impact Mapper, 2 Scenario Builder, 3 Regime Finder, 4 Risk Engine, 5 Validator, 6 Report Writer. 시나리오 입구는 0·1이 `skip`.
`retry`: Validator가 반려해 해당 Agent가 다시 실행되기를 기다리는 상태. 반려가 한 번이라도 있었던 실행은 `run.retry_loops`에 `[{"from_idx": 5, "to_idx": 1}]`가 들어 있습니다 (타임라인 반려 루프 화살표용).

## GET `/api/runs/{id}/stream` — SSE

`text/event-stream`. 상태가 바뀔 때마다 아래 이벤트를 보냅니다. 모든 이벤트의 `data`에는 전체 타임라인이 들어 있어 프론트엔드는 받는 대로 교체하면 됩니다.

| event | 시점 |
| --- | --- |
| `snapshot` | 연결 직후 현재 타임라인 전체 (실행 중일 때만) |
| `step_started` | 단계 시작 |
| `step_finished` | 단계 완료 |
| `step_retry` | Validator 반려 → 대상 Agent 재실행 |
| `step_failed` | 단계 실패 |
| `run_finished` | 실행 종료 (마지막 이벤트, 이후 연결 종료) |

```json
{"run_id": "…", "status": "running", "elapsed_ms": 4200, "current": "Impact Mapper — 파급 경로 추론 (2차 시도)", "step": {/* 바뀐 Step */}, "steps": [/* Step 7개 */], "retry_loops": []}
```

`run_finished` 수신 후 `GET /api/runs/{id}`로 전체 결과를 다시 받습니다. 이미 끝난 실행에 연결하면 `run_finished` 하나만 보내고 닫습니다. 15초마다 `: keep-alive` 주석을 보냅니다.

## PATCH `/api/runs/{id}/scenario`

요청: `{"shocks": [{"variable": "USDKRW", "change": 7.0}]}` (변경할 변수만 보내도 됨)
응답: `{"run_id": "새 run_id"}` — 새 실행은 Regime Finder부터 진행하고, 0~2단계는 이전 결과를 재사용(`done`, note "이전 실행 결과 재사용")합니다.

## GET `/api/runs/{id}/calc-log` — 계산 근거(S5)

```json
{
  "calc_id": "calc_…", "run_id": "…", "code_hash": "sha256:…", "engine_version": "0.1.0", "created_at": "…",
  "sources": [{"name": "FRED · DGS10", "collected_at": "2026-10-13", "synthetic": false}],
  "entries": {
    "pnl": {
      "title": "포트폴리오 예상 손익", "value": -3.8, "value_text": "−3.8%", "sub": "−1,240억 원 · 20영업일 · 가상 모델 포트폴리오 A",
      "formula": "ΔRᵢ = Σₖ βᵢₖ · Δfₖ\nΔP = Σᵢ wᵢ · ΔRᵢ",
      "columns": ["팩터", "포트폴리오 β", "충격값", "기여"],
      "rows": [[{"v": "원/달러 환율"}, {"v": "−0.310"}, {"v": "+5.0%"}, {"v": "−1.55%p", "num": -1.55}]],
      "note": "…"
    }
  },
  "inputs": {}, "outputs": {}
}
```

열리는 키: `pnl`, `amt`, `range`, `model`, `reg`, `h:{asset_id}`, `fc:{factor_id}`, `f:{factor_id}`. 셀에 `num`이 있으면 손익색과 굵게(700)를 적용합니다. 첫 열은 좌측, 나머지는 우측 정렬.

## GET `/api/runs/{id}/report?format=md|html`

`md`(기본): `text/markdown` 파일 다운로드. `html`: 인쇄용 HTML (브라우저 인쇄로 PDF 저장).

## GET `/api/runs`

```json
[{"run_id": "…", "created_at": "…", "entry": "event", "title": "…", "portfolio_name": "…", "portfolio_pnl": -3.8, "validation_status": "pass|warn|fail", "status": "done"}]
```

## GET `/api/series/{id}?start=&end=`

```json
{"series_id": "DGS10", "name": "…", "unit": "%", "source": "FRED", "license": "…", "points": [{"date": "2026-10-13", "value": 4.12}]}
```

## GET `/api/data/status` — 데이터 관리 화면(S7), 토큰 불필요

```json
{
  "llm_mode": "anthropic | offline", "model_default": "claude-haiku-5-5", "model_impact_mapper": "…",
  "synthetic_remaining": ["KOSPI_IT"],
  "quality_issues": ["KTB3Y"],
  "series": [{"series_id": "USDKRW", "name": "원/달러 환율", "source": "한국은행 ECOS", "unit": "KRW", "license": "…", "source_url": "…",
              "count": 2705, "first_date": "2015-10-19", "last_date": "2026-10-14", "collected_at": "2026-10-14T08:29:10",
              "synthetic": false, "in_use": true, "role": "factor | asset | other", "factor_name": "원/달러 환율",
              "stale_bdays": 1, "coverage": 0.962, "quality": "ok | stale | gappy | synthetic | empty"}],
  "events": [{"source": "Federal Register", "is_demo": false, "count": 321, "first_date": "…", "last_date": "…"}],
  "collectors": [{"name": "fred", "description": "FRED → DGS10, DGS2, DXY_BROAD, WTI, (FED_TARGET_UPPER)", "required_key": "FRED_API_KEY", "key_present": true}],
  "collect": {"running": false, "started_at": "…", "finished_at": "…", "next_scheduled_at": "…", "error": null,
              "reports": [{"collector": "krx_prices", "status": "ok | skipped | error", "message": "…", "counts": {"KOSPI": 1662}}]},
  "admin_enabled": true, "daily_hour_utc": 0
}
```

시계열 품질 필드: `stale_bdays` = 최종 관측일 이후 지난 영업일 수, `coverage` = 기간 내 영업일 대비 관측 비율(0~1).
`quality` 는 `synthetic`(합성) → `stale`(5영업일 초과 지연) → `gappy`(커버리지 85% 미만) → `ok` 순으로 판정하며 값이 없으면 `empty`.
계단형 시계열(`BOK_BASE_RATE`, `FED_TARGET_UPPER`)은 지연 20영업일까지, 주 1회 반영되는 `WTI`는 10영업일까지 정상으로 본다. `quality_issues` 는 사용 중(`in_use`)인데 `stale|gappy|empty` 인 시리즈 id 목록.

## 관리용 (헤더 `X-Admin-Token` 또는 `?token=`)

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| POST | `/api/admin/collect` body `{since?, only?: ["fred", …]}` | 수집 시작 (202). 진행 중이면 409 |
| GET | `/api/admin/collect/run?token=&since=&only=a,b` | 브라우저용 수집 시작 |
| GET | `/api/admin/collect/status` | 진행 상황 (`collect` 객체와 동일) |

`ADMIN_TOKEN`이 비어 있으면 404. 토큰이 틀리면 403.
