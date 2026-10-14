# 배포 가이드 (데모 URL 제출용)

본선 제출물 "프로토타입(데모 URL)"은 실행 가능한 링크여야 한다. 아래 두 방식 중 하나를 쓴다.

## A. Docker Compose (단일 VM) — 권장

```bash
git clone https://github.com/uccwal/ripple.git && cd ripple
cp .env.example .env            # ANTHROPIC_API_KEY, FRED/ECOS/공공데이터 키 입력
docker compose up --build -d    # db + frontend-build + api(:8000) + collector
docker compose logs -f api
```

- `http://<호스트>:8000` — 프론트엔드(정적 빌드)와 API를 같은 포트에서 서빙한다.
- 첫 기동 시 `python -m app.seed --synthetic`이 실행되어 키가 없어도 화면이 동작한다 (상단 '합성 데이터' 배지).
- `collector` 컨테이너가 하루 1회 `collectors.run_all`을 실행한다. 키가 있는 수집기만 동작하며, 실제 데이터가 들어오면 같은 `series_id`의 합성 값을 덮어쓴다.
- 처음 실제 데이터를 넣을 때는 5년치 적재: `docker compose run --rm collector python -m collectors.run_all --since 2015-01-01`
- HTTPS가 필요하면 앞에 Caddy/nginx를 두고 `8000`으로 프록시한다 (SSE를 위해 프록시 버퍼링 끄기: nginx `proxy_buffering off;`).

## B. 분리 배포 (프론트 정적 호스팅 + API 서버)

1. API: `backend/Dockerfile`로 이미지 빌드 → Fly.io / Railway / Cloud Run 등에 배포. 환경 변수 `DATABASE_URL`(PostgreSQL), `ANTHROPIC_API_KEY`, `CORS_ORIGINS=https://<프론트 도메인>`.
2. 프론트: `cd frontend && VITE_API_BASE=https://<API 도메인> npm run build` → `dist/`를 Vercel/Netlify/Cloudflare Pages에 올린다.
3. SSE(`/api/runs/{id}/stream`)가 통과하는지 확인한다 (일부 PaaS는 응답 버퍼링을 한다).

## 심사 기간 운영 체크리스트

- [ ] `.env`에 실제 키 설정, `LLM_MODE` 비움 → `/api/meta`의 `llm_mode`가 `anthropic`
- [ ] 수집기 실행 후 `/api/meta`의 `synthetic_data`가 `false`
- [ ] 데모 시나리오 3개를 미리 실행해 결과를 캐시(실행 이력에 남김) — 심사 중 API 장애 대비
- [ ] `scripts/backtest.py --json docs/submission/backtest.json` 결과를 발표 자료에 반영
- [ ] 저장소 README의 실행 방법·사용 기술·데이터 출처 최신화
