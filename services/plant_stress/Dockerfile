FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/

# ברירות מחדל (אפשר לשנות ב-run)
ENV INPUT_DIR=/data/inbox \
    MODEL_DIR=/models \
    PERIOD_DAYS=7 \
    CONF_THRESHOLD=0.0 \
    POSTGRES_DSN="postgresql://postgres:pg123@host.docker.internal:5432/missions_db"

CMD ["python", "/app/app.py"]
