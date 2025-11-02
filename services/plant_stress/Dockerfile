FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY certs /app/certs

RUN if [ -f /app/certs/netfree-ca.crt ]; then \
    echo "Installing NetFree certificate..."; \
    cp /app/certs/netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt && \
    update-ca-certificates; \
    else \
    echo "⚠️ WARNING: netfree-ca.crt not found, continuing without it."; \
    fi

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    --trusted-host pypi.org \
    --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org

COPY src/ /app/

ENV INPUT_DIR=/data/inbox \
    MODEL_DIR=/models \
    PERIOD_DAYS=7 \
    CONF_THRESHOLD=0.0 \
    POSTGRES_DSN="postgresql://postgres:pg123@host.docker.internal:5432/missions_db"

CMD ["python", "/app/app.py"]
