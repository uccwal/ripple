# 외부 자원 사용 기록

공모전 규칙("사용하는 모든 외부 자원에 대해 명확하게 기록을 유지하고 제출 작업물에 출처를 명시")에 따른 목록. 데이터 출처는 [`data/SOURCES.md`](../data/SOURCES.md)에 따로 정리한다.

## AI 모델·API

| 자원 | 용도 | 조건 |
| --- | --- | --- |
| Anthropic Claude API — `claude-haiku-5-5` (기본), `claude-sonnet-5-5` (본선 Impact Mapper) | Event Analyst·Impact Mapper·Scenario Builder·Report Writer의 구조화 출력 | 유료 API, Anthropic 이용약관 준수. 숫자 계산에는 쓰지 않음 |

## 오픈소스 라이브러리

| 구분 | 라이브러리 | 라이선스 |
| --- | --- | --- |
| 백엔드 | FastAPI, Uvicorn, SQLAlchemy, Pydantic, LangGraph, anthropic SDK, NumPy, pandas, python-dotenv, Python-Markdown, psycopg2, httpx, pytest | MIT / BSD / Apache-2.0 / LGPL(psycopg2) |
| 프론트엔드 | Vue 3, Vite, TypeScript, Pinia, Vue Router, Tailwind CSS, ECharts, Vue Flow, marked, DOMPurify | MIT / Apache-2.0 |
| 폰트 | Pretendard Variable (orioncactus) | SIL OFL 1.1 |
| 인프라 | PostgreSQL, Docker | PostgreSQL License / Apache-2.0 |

정확한 버전은 `backend/requirements.txt`, `frontend/package.json`에 있다.

## 개발 도구

- 설계·구현 과정에서 Claude Code(AI 코딩 도구)를 사용했다. 설계·검증·문서는 팀이 검토·수정했다.

## 사용하지 않은 것 (의도적으로)

- S&P 500 등 제3자 저작권이 걸린 해외 주가지수 시계열 → 국내 상장 해외지수 ETF 시세로 대체
- 미국 관보 로고·인장, 기관 로고 → 텍스트 출처 표기만
- 실제 기관 보유내역 → 가상 모델 포트폴리오만 사용, 화면에 상시 배지 표시
