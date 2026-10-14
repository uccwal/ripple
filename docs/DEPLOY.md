# 배포 가이드 (데모 URL 제출용)

본선 제출물 "프로토타입(데모 URL)"은 실행 가능한 링크여야 한다. 아래 세 방식 중 하나를 쓴다.

**GitHub Pages만으로는 안 된다.** Pages는 정적 파일만 호스팅하므로 프론트엔드는 올릴 수 있지만, Agent·계산·DB·Claude 호출을 하는 백엔드(Python)는 별도 서버가 필요하다. 가장 빠른 무료 조합은 **C. GitHub Pages(프론트) + Render(백엔드)** 다.

## C. GitHub Pages + Render — 무료, 클릭 몇 번 (권장 시작점)

이 저장소에 설정이 들어 있다: `.github/workflows/pages.yml`(프론트 → Pages), `render.yaml`(백엔드 + PostgreSQL → Render).

1. **백엔드(Render)**: https://dashboard.render.com → New → **Blueprint** → `uccwal/ripple` 선택 → `render.yaml`이 읽힌다 → 환경 변수 `ANTHROPIC_API_KEY`(필수), `FRED_API_KEY`·`ECOS_API_KEY`·`DATA_GO_KR_API_KEY`(선택) 입력 → Apply. 몇 분 뒤 `https://ripple-api.onrender.com` 같은 URL이 생긴다. `…/healthz`가 `{"ok":true}`면 성공.
2. **프론트엔드(Pages)**: 저장소 Settings → Pages → Source를 **GitHub Actions**로. Settings → Secrets and variables → Actions → **Variables** 탭 → `API_BASE_URL` = 1번에서 받은 URL. 그 다음 `main`에 푸시(또는 Actions 탭에서 "Deploy frontend to GitHub Pages" 수동 실행) → `https://uccwal.github.io/ripple/`.
3. 백엔드 `CORS_ORIGINS`는 `render.yaml`에 `https://uccwal.github.io`로 들어 있다. 다른 도메인이면 Render 환경 변수에서 고친다.

주의: Render 무료 플랜은 15분 동안 요청이 없으면 잠들어 첫 요청이 30~60초 걸린다. 심사 직전에 한 번 열어 깨우거나, 유료 플랜(월 7달러)으로 올린다. 무료 PostgreSQL은 90일 후 만료되므로 본선 기간(12월) 전에 생성하는 것이 좋다.

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

## 실데이터로 바꾸기 (합성 데이터 배지 제거)

Render 무료 서버는 재시작하면 컨테이너 안 SQLite가 지워지므로, 실데이터를 유지하려면 Postgres를 먼저 붙인다.

1. **Postgres**: Render → New → Postgres (Free) → 생성 후 **Internal Database URL** 복사 → Web Service 환경 변수 `DATABASE_URL`에 붙여넣기 (재배포됨).
2. **API 키 발급** (모두 무료, 발급 즉시 사용):
   | 키 | 발급처 | 시간 |
   | --- | --- | --- |
   | `FRED_API_KEY` | https://fred.stlouisfed.org/docs/api/api_key.html (계정 → Request API key) | 즉시 |
   | `ECOS_API_KEY` | https://ecos.bok.or.kr → 로그인 → 인증키 신청 | 즉시~수 분 |
   | `DATA_GO_KR_API_KEY` | https://www.data.go.kr → 회원가입 → "금융위원회_지수시세정보", "금융위원회_증권상품시세정보" 각각 **활용신청** → 마이페이지 → 일반 인증키(Decoding) | 자동승인, 1시간 안팎 |
3. Web Service 환경 변수에 세 키와 `ADMIN_TOKEN`(아무 긴 문자열), `COLLECT_DAILY_HOUR_UTC=0`(매일 09:00 KST 자동 수집) 추가.
4. 첫 적재(5년치)는 수동으로 한 번:
   ```bash
   curl -X POST https://<api-host>/api/admin/collect -H "X-Admin-Token: <ADMIN_TOKEN>" \
        -H "content-type: application/json" -d '{"since": "2015-01-01"}'
   curl https://<api-host>/api/admin/collect/status -H "X-Admin-Token: <ADMIN_TOKEN>"   # 진행 상황
   ```
   끝나면 `/api/meta`의 `synthetic_data`가 `false`가 되고 화면 상단 배지가 사라진다. 이후엔 매일 자동 수집된다.
5. 수집기가 `error`를 돌려주면 `data/SOURCES.md` §5의 "확인 필요" 항목(ECOS 통계코드, KRX 지수명·ETF 코드)을 실제 응답에 맞춰 고친다.

## 심사 기간 운영 체크리스트

- [ ] `.env`에 실제 키 설정, `LLM_MODE` 비움 → `/api/meta`의 `llm_mode`가 `anthropic`
- [ ] 수집기 실행 후 `/api/meta`의 `synthetic_data`가 `false`
- [ ] 데모 시나리오 3개를 미리 실행해 결과를 캐시(실행 이력에 남김) — 심사 중 API 장애 대비
- [ ] `scripts/backtest.py --json docs/submission/backtest.json` 결과를 발표 자료에 반영
- [ ] 저장소 README의 실행 방법·사용 기술·데이터 출처 최신화
