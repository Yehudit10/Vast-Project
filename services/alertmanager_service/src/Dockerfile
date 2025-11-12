# ─────────────────────────────────────────────
# Dockerfile (used for both alert_service and gateway)
# ─────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

COPY certs/*.crt /usr/local/share/ca-certificates/
RUN chmod 644 /usr/local/share/ca-certificates/*.crt \
 && update-ca-certificates

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

RUN python -m pip install --upgrade --no-cache-dir pip setuptools wheel

# Copy code
COPY . .

# Install deps
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pyyaml aiohttp asyncpg


# Default port — can be overridden by compose
EXPOSE 8090

# Default environment
ENV CFG_PATH=/app/templates.yml
ENV ALERTMANAGER_URL=http://alertmanager:9093
ENV GATEWAY_URL=http://alerts-gateway:8000/internal/alert


# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
