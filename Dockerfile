# 저장소 루트 Dockerfile — Render 등 PaaS가 자동 인식하도록 둔다. 내용은 backend/Dockerfile 과 같다.
# 빌드 컨텍스트는 저장소 루트.
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend
COPY collectors ./collectors
COPY data ./data
WORKDIR /app/backend
EXPOSE 8000
# Render는 PORT 환경 변수를 준다. 없으면 8000.
CMD ["sh", "-c", "python -m app.seed ${SEED_ARGS:---synthetic} && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
