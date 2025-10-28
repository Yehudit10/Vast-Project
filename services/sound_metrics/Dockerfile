FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV AUDIO_DIR=/data/audio \
    ADDR=0.0.0.0 \
    PORT=8001 \
    WINDOW_MIN=5 \
    FRAME_SEC=0.1 \
    THRESHOLD=0.01 \
    STABLE_SEC=5 \
    USE_UTC=false

EXPOSE 8001
CMD ["python", "src/local_metrics.py"]
