# RIPPLE 프론트엔드

정책 파급 스트레스 테스트 Agent의 화면(S1–S6). Vue 3 + Vite + TypeScript, Pinia, Vue Router, Tailwind CSS v3, ECharts, Vue Flow.
시각 기준은 `docs/design/README.md`(핸드오프)와 `tokens.css` / `tailwind.tokens.js`, API는 `docs/API_CONTRACT.md`를 따릅니다.

## 실행

```bash
# 백엔드 (별도 터미널, :8000)
cd backend && uvicorn app.main:app --port 8000

# 프론트엔드 (:5173, /api → http://127.0.0.1:8000 프록시)
cd frontend
npm install
npm run dev
```

`.npmrc`의 `legacy-peer-deps=true`는 npm 10.9가 vitest 4의 선택적 peer를 풀다가 충돌하는 문제를 피하기 위한 설정입니다. 필요한 peer는 `package.json`에 모두 명시되어 있습니다.

## 스크립트

| 명령 | 내용 |
| --- | --- |
| `npm run dev` | 개발 서버 (포트 5173 고정) |
| `npm run build` | `vue-tsc` 타입 검사 후 `dist/` 빌드. 백엔드는 `frontend/dist`가 있으면 같은 서버에서 서빙합니다 |
| `npm run preview` | 빌드 결과 미리보기 (:4173, 같은 프록시) |
| `npm run typecheck` | 타입 검사만 |
| `npm test` | vitest 단위 테스트 (수치 서식·부호·손익색, 그래프 배치, 보고서 렌더링) |

## 화면과 라우트

| 라우트 | 화면 |
| --- | --- |
| `/` | S1 이벤트 대시보드 |
| `/new` | S2 새 분석 (`?event=<id>`, `?entry=scenario`) |
| `/runs/:id` | S3 분석 워크스페이스 (`?tab=path\|scen\|result\|report`) |
| `/portfolios` | S4 포트폴리오 |
| `/runs` | S6 실행 이력 |
| `/system` | 컴포넌트·토큰 (개발 참고용) |

S5 계산 근거 패널은 전역 슬라이드 오버입니다. `uiStore.openCalc(runId, key)`로 열고, `GET /api/runs/{id}/calc-log`를 실행별로 캐시합니다.

## 구조

```
src/
  api/          client.ts (fetch 래퍼·오류), types.ts (API_CONTRACT 타입)
  stores/       meta · ui(S5 패널·토스트) · calcLog · events · portfolios · history
                liveRuns (SSE 세션 관리: 실행 중 pill·완료 토스트) · run (S3 상태·시나리오 초안)
  components/
    common/     상단 바, 버튼·배지·칩, CalcNum(클릭 가능한 수치), 스켈레톤·빈 상태·오류, CalcPanel(S5), 토스트
    s1/ s3/ s4/ 화면별 컴포넌트 (s3/graph: Vue Flow 노드·엣지·배치 알고리즘)
  views/        라우트 화면
  utils/        format.ts (U+2212 부호·손익색·단위), labels.ts, report.ts (Markdown → DOMPurify)
  styles/       tokens.css (핸드오프 사본), main.css
```

## 구현 메모

- **수치 표기**: 모든 수치는 `utils/format.ts`를 거칩니다. 음수는 U+2212, 양수는 `+`, 반올림 후 0이면 부호 없음. 손익색은 국내식(이익 `#D23F31`, 손실 `#1E5BD8`).
- **실시간 진행**: 진행 중 실행은 `EventSource(/api/runs/{id}/stream)`로 받고, 각 이벤트의 `steps`로 타임라인을 교체합니다. `run_finished` 후 RunState를 다시 받습니다. 스트림이 끊기면 1.5초 폴링으로 대체합니다.
- **반려 루프 화살표**: `retry_loops`의 두 단계 아이콘 위치를 DOM에서 재고, 펼침 등으로 높이가 바뀌면 ResizeObserver로 다시 잽니다.
- **파급 경로 그래프**: Vue Flow를 zoom 1로 고정해 정적 다이어그램으로 씁니다. 4열 배치는 `s3/graph/layout.ts`(barycenter 정렬 + 겹침 해소)가 캔버스 폭에 맞춰 px 좌표를 계산합니다.
- **자산별 손익 막대**는 CSS 그리드로 그렸습니다. 행 hover 배경, 행 클릭 → S5, 점선 밑줄 수치를 스펙대로 맞추기 위해서입니다(`AssetPnlBars.vue` 주석 참고). 도넛(S4)은 ECharts입니다.
- **보고서**: 백엔드가 수치를 `<!--k:KEY-->…<!--/k-->`로 감싸 보내므로, 이 마커를 S5 키로 바꿔 보고서 안 수치도 클릭할 수 있게 합니다. HTML은 DOMPurify로 정리합니다.
- **폰트**: Pretendard는 핸드오프에 적힌 jsDelivr CDN에서 불러옵니다.
