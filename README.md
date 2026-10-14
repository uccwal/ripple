# RIPPLE

정책 파급 스트레스 테스트 Agent. 정책 발표나 직접 입력한 시나리오가 포트폴리오에 미치는 영향을 파급 경로, 시나리오, 손익, 보고서 순으로 보여줍니다.

## 문서
- [시스템 설계서](docs/DESIGN.md)
- [UI 디자인 핸드오프 (S1–S6)](docs/design/README.md)

## 구조
```
backend/     FastAPI + LangGraph (agents, engine, models, prompts)
collectors/  FRED, ECOS, 시세, Federal Register, 정책브리핑 수집기
frontend/    Vue 3 + Vite + TS (S1–S6)
data/        가상 포트폴리오, 출처·라이선스 목록
docs/        설계서, 디자인 핸드오프
```

## 기술 스택
Python · FastAPI · LangGraph · PostgreSQL · Vue 3 · Pinia · Tailwind · ECharts · Vue Flow · Docker Compose
