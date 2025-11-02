FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# COPY certs/ /app/certs/
# RUN if [ -d /app/certs ] && ls /app/certs/*.crt >/dev/null 2>&1; then \
#       cp /app/certs/*.crt /usr/local/share/ca-certificates/ && update-ca-certificates; \
#     else \
#       echo "No extra CA certs found. Skipping CA update."; \
#     fi
COPY certs/ /app/certs/
RUN if ls /app/certs/*.crt >/dev/null 2>&1; then \
      cp /app/certs/*.crt /usr/local/share/ca-certificates/ && \
      chmod 644 /usr/local/share/ca-certificates/*.crt && \
      update-ca-certificates; \
    else \
      echo "No extra CA certs found. Skipping CA update."; \
    fi

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

RUN printf "[global]\ncert = /etc/ssl/certs/ca-certificates.crt\n" > /etc/pip.conf

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt

# Python deps
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY src/ ./src/

ENV PYTHONUNBUFFERED=1 \
    ADDR=0.0.0.0 \
    PORT=8001 \
    WINDOW_MIN=5 \
    FRAME_SEC=0.1 \
    THRESHOLD=0.01 \
    USE_UTC=false \
    MINIO_ENDPOINT=minio:9000 \
    MINIO_ACCESS_KEY=minioadmin \
    MINIO_SECRET_KEY=minioadmin123 \
    MINIO_BUCKET=audio \
    MINIO_PREFIX=samples/

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
  CMD curl -fsS http://localhost:8001/metrics >/dev/null || exit 1

CMD ["python", "-u", "src/metrics.py"]
