FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

<<<<<<< HEAD

# COPY certs/ /app/certs/
# RUN if [ -d /app/certs ] && ls /app/certs/*.crt >/dev/null 2>&1; then \
#       cp /app/certs/*.crt /usr/local/share/ca-certificates/ && update-ca-certificates; \
=======
>>>>>>> 4bb2e60fc0fd9a846955fa89533d661a56b1645a
# Bring in app files (including optional ./certs)
COPY . .

# Install any *.crt in ./certs (if present), regardless of file names
RUN if [ -d /app/certs ] && [ -n "$(find /app/certs -type f -name '*.crt' -print -quit)" ]; then \
      find /app/certs -type f -name '*.crt' -exec cp {} /usr/local/share/ca-certificates/ \; && \
      update-ca-certificates; \
    else \
      echo "No extra CA certs found. Skipping CA update."; \
    fi


COPY requirements.txt .
# Ensure pip/requests use the system CA bundle (includes optional NetFree certs)
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    # CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Persist pip setting as fallback
RUN printf "[global]\ncert = /etc/ssl/certs/ca-certificates.crt\n" > /etc/pip.conf

# Python deps (now benefit from the updated CA store if certs exist)
RUN pip install --no-cache-dir -r requirements.txt

# App code already copied above
ENV PYTHONUNBUFFERED=1 \
    ADDR=0.0.0.0 \
    PORT=8005 \
    WINDOW_MIN=5 \
    FRAME_SEC=0.1 \
    THRESHOLD=0.01 \
    USE_UTC=false \
    MINIO_ENDPOINT=minio:9000 \
    MINIO_ACCESS_KEY=minioadmin \
    MINIO_SECRET_KEY=minioadmin123 \
    MINIO_BUCKET=sound \
    MINIO_PREFIX=sounds/

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
  CMD curl -fsS http://localhost:8005/metrics >/dev/null || exit 1

CMD ["python", "-u", "src/metrics.py"]
