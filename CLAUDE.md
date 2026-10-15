# CLAUDE.md

- 설계 기준: `docs/DESIGN.md` (아키텍처, Agent 명세, 계산 로직, 데이터 모델, API, 화면, 구조)
- UI 기준: `docs/design/README.md` + `tokens.css` / `tailwind.tokens.js`. 프로토타입 HTML은 레퍼런스이며 그대로 옮기지 않는다.
- 수치는 `backend/app/engine`에서만 계산한다. LLM은 숫자를 만들지 않고 `calc_log` 결과만 인용한다.
- 손익 색상은 국내식(이익 빨강 `#D23F31`, 손실 파랑 `#1E5BD8`).
- 기본 모델 `claude-haiku-5-5`, Impact Mapper는 `claude-sonnet-5-5` (환경 변수 `MODEL_IMPACT_MAPPER`로 변경).
- API 응답 형태는 `docs/API_CONTRACT.md`가 기준. 바꾸면 문서와 프론트엔드 타입(`frontend/src/api/types.ts`)을 함께 고친다.
- 공모전 요건·평가 기준은 `docs/COMPETITION.md`. 제출 원고는 `docs/submission/`.
- 테스트: `cd backend && python -m pytest tests -q`, `cd frontend && npm run build && npx vitest run`.
- 외부 데이터는 공개 API만, 출처·수집일·라이선스를 `series.license`에 남긴다. 제3자 지수(S&P 500 등) 금지.
