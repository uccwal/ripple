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
CMD ["sh", "-c", "python -m app.seed ${SEED_ARGS:---synthetic} && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
