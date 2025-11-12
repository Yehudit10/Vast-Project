# ─────────────────────────────────────────────
# Dockerfile (used for both alert_service and gateway)
# ─────────────────────────────────────────────
FROM python:3.11-slim

# System CA tools (needed for optional NetFree certs)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy code (including optional ./certs)
COPY . .

# If ./certs has any *.crt (at any depth) → add to system trust store; otherwise skip
RUN if [ -d /app/certs ] && [ -n "$(find /app/certs -type f -name '*.crt' -print -quit)" ]; then \
      find /app/certs -type f -name '*.crt' -exec cp {} /usr/local/share/ca-certificates/ \; && \
      update-ca-certificates; \
    else \
      echo "No extra CA certs found. Skipping CA update."; \
    fi

# Ensure pip/requests use the system CA bundle (works with/without NetFree)
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Persist pip setting as fallback
RUN printf "[global]\ncert = /etc/ssl/certs/ca-certificates.crt\n" > /etc/pip.conf

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
