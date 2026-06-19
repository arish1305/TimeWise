FROM python:3.11-slim

WORKDIR /app

COPY ai_engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai_engine/ .
COPY common/ ./common/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
