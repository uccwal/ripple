# CLAUDE.md

- 설계 기준: `docs/DESIGN.md` (아키텍처, Agent 명세, 계산 로직, 데이터 모델, API, 화면, 구조)
- UI 기준: `docs/design/README.md` + `tokens.css` / `tailwind.tokens.js`. 프로토타입 HTML은 레퍼런스이며 그대로 옮기지 않는다.
- 수치는 `backend/app/engine`에서만 계산한다. LLM은 숫자를 만들지 않고 `calc_log` 결과만 인용한다.
- 손익 색상은 국내식(이익 빨강 `#D23F31`, 손실 파랑 `#1E5BD8`).
- 기본 모델 `claude-haiku-5-5`, 본선 튜닝 시 Impact Mapper만 `claude-sonnet-5-5`.
