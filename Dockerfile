FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY sql ./sql

# Le pipeline alimente l'entrepôt, puis l'API le sert
CMD ["sh", "-c", "python -m energy.pipeline && uvicorn energy.api.main:app --host 0.0.0.0 --port 8000"]
EXPOSE 8000
