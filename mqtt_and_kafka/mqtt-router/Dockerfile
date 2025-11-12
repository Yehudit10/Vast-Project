FROM python:3.12-slim

# ---- Build-time toggle for NetFree CA injection ----
ARG USE_NETFREE=false

# ---- System deps (CA, curl). librdkafka1 helps if confluent-kafka wheel is not fully static on your base ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl librdkafka1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Optional NetFree certificates (mount or COPY your certs/*.crt alongside the Dockerfile) ----
# If you keep certs in repo, uncomment the next line:
# COPY certs/*.crt /app/certs/
RUN if [ "$USE_NETFREE" = "true" ] && [ -d /app/certs ] && ls /app/certs/*.crt >/dev/null 2>&1; then \
      echo "Configuring NetFree certificates..."; \
      cp /app/certs/*.crt /usr/local/share/ca-certificates/ && update-ca-certificates; \
    else \
      echo "No NetFree certs applied (USE_NETFREE=$USE_NETFREE)."; \
    fi

# ---- Make requests/libs use system CA (works both with and without NetFree) ----
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PYTHONUNBUFFERED=1

# ---- Install Python deps ----
COPY requirements.txt .
# When behind NetFree, trusted-host can help even אם אין צורך זה לא מזיק:
RUN python -m pip install --no-cache-dir \
      --trusted-host pypi.org --trusted-host files.pythonhosted.org \
      -r requirements.txt

# ---- App code ----
COPY app.py .

ENTRYPOINT ["python", "app.py"]
