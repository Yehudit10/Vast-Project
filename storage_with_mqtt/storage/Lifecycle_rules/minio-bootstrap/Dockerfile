FROM alpine:3.19
# ===== Deps & Binaries =====
RUN apk add --no-cache bash curl ca-certificates supervisor && \
  update-ca-certificates && \
  curl -k -fsSL https://dl.min.io/server/minio/release/linux-amd64/minio -o /usr/local/bin/minio && \
  curl -k -fsSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc && \
  chmod +x /usr/local/bin/minio /usr/local/bin/mc

# Download MinIO binaries with retry logic
RUN for i in 1 2 3 4 5; do \
  curl -k -fsSL https://dl.min.io/server/minio/release/linux-amd64/minio -o /usr/local/bin/minio && break || \
  (echo "Retry $i/5 for minio..." && sleep 5); \
  done && \
  chmod +x /usr/local/bin/minio

RUN for i in 1 2 3 4 5; do \
  curl -k -fsSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc && break || \
  (echo "Retry $i/5 for mc..." && sleep 5); \
  done && \
  chmod +x /usr/local/bin/mc
# ===== Dirs =====
RUN mkdir -p /data/hot /data/cold /entrypoint /config /var/log/supervisor
# ===== init.sh (Bootstrap) =====
RUN cat > /entrypoint/init.sh <<'SH' && chmod +x /entrypoint/init.sh
#!/usr/bin/env bash
set -euo pipefail
: "${MINIO_ROOT_USER:?Missing MINIO_ROOT_USER}"
: "${MINIO_ROOT_PASSWORD:?Missing MINIO_ROOT_PASSWORD}"
: "${MC_ALIAS_HOT:=hot}"
: "${MC_ALIAS_COLD:=cold}"
: "${HOT_ENDPOINT:=http://minio-hot:9000}"
: "${COLD_ENDPOINT:=http://minio-cold:9000}"
# Configure mc aliases (idempotent)
mc alias set "${MC_ALIAS_HOT}"  "${HOT_ENDPOINT}"  "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" || true
mc alias set "${MC_ALIAS_COLD}" "${COLD_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" || true
echo "[bootstrap] checking HTTP readiness..."
until curl -sf "${HOT_ENDPOINT}/minio/health/live"  >/dev/null; do sleep 1; done
until curl -sf "${COLD_ENDPOINT}/minio/health/live" >/dev/null; do sleep 1; done
echo "[bootstrap] waiting for hot (${HOT_ENDPOINT})..."
until mc ls "${MC_ALIAS_HOT}"  >/dev/null 2>&1; do sleep 2; done
echo "[bootstrap] waiting for cold (${COLD_ENDPOINT})..."
until mc ls "${MC_ALIAS_COLD}" >/dev/null 2>&1; do sleep 2; done

# Enable versioning on HOT buckets
echo "[bootstrap] enabling versioning..."
mc version enable "${MC_ALIAS_HOT}/imagery"   || true
mc version enable "${MC_ALIAS_HOT}/telemetry" || true

echo "[bootstrap] ensuring remote tiers exist on HOT..."
# imagery → COLD/imagery
if ! mc ilm tier ls "${MC_ALIAS_HOT}" --json | grep -q '"Name":"COLD_IMAGERY"'; then
  mc ilm tier add s3 "${MC_ALIAS_HOT}" COLD_IMAGERY \
    --endpoint   "${COLD_ENDPOINT}" \
    --access-key "${MINIO_ROOT_USER}" \
    --secret-key "${MINIO_ROOT_PASSWORD}" \
    --bucket imagery \
    --region us-east-1 || true
fi
# telemetry → COLD/telemetry
if ! mc ilm tier ls "${MC_ALIAS_HOT}" --json | grep -q '"Name":"COLD_TELEMETRY"'; then
  mc ilm tier add s3 "${MC_ALIAS_HOT}" COLD_TELEMETRY \
    --endpoint   "${COLD_ENDPOINT}" \
    --access-key "${MINIO_ROOT_USER}" \
    --secret-key "${MINIO_ROOT_PASSWORD}" \
    --bucket telemetry \
    --region us-east-1 || true
fi

echo "[bootstrap] applying lifecycle policies (per bucket)..."
# --- IMAGERY ---
mc ilm rule rm "${MC_ALIAS_HOT}/imagery" --all --force || true
if [ -s "/config/lifecycle-imagery.json" ]; then
  mc ilm import "${MC_ALIAS_HOT}/imagery" < "/config/lifecycle-imagery.json" || true
else
  echo "[bootstrap] /config/lifecycle-imagery.json not found; applying fallback"
  mc ilm rule add "${MC_ALIAS_HOT}/imagery" \
    --transition-days 7 \
    --transition-tier COLD_IMAGERY || true
fi
# --- TELEMETRY ---
mc ilm rule rm "${MC_ALIAS_HOT}/telemetry" --all --force || true
if [ -s "/config/lifecycle-telemetry.json" ]; then
  mc ilm import "${MC_ALIAS_HOT}/telemetry" < "/config/lifecycle-telemetry.json" || true
else
  echo "[bootstrap] /config/lifecycle-telemetry.json not found; applying fallback"
  mc ilm rule add "${MC_ALIAS_HOT}/telemetry" \
    --transition-days 7 \
    --transition-tier COLD_TELEMETRY || true
fi

echo "[bootstrap] current rules:"
mc ilm rule ls "${MC_ALIAS_HOT}/imagery"   || true
mc ilm rule ls "${MC_ALIAS_HOT}/telemetry" || true

# ===============================================
# Kafka Event Notifications
# ===============================================
echo "[bootstrap] waiting for Kafka broker..."
until nc -z kafka 9092 >/dev/null 2>&1; do sleep 3; done
echo "[bootstrap] Kafka is reachable."

echo "[bootstrap] waiting for MinIO Kafka notifiers to load..."
until mc admin config get "${MC_ALIAS_HOT}" notify_kafka | grep -q "notify_kafka:primary" && \
      mc admin config get "${MC_ALIAS_HOT}" notify_kafka | grep -q "notify_kafka:images"; do
  echo "[bootstrap] Kafka notifiers not ready yet... retrying..."
  sleep 3
done
echo "[bootstrap] Kafka notifiers 'primary' and 'images' are loaded."

echo "[bootstrap] removing old event rules..."
mc event remove "${MC_ALIAS_HOT}/imagery" --force >/dev/null 2>&1 || true
mc event remove "${MC_ALIAS_HOT}/telemetry" --force >/dev/null 2>&1 || true

echo "[bootstrap] adding Kafka event rules..."
# Rule 1: sound/ prefix → topic sound.new (via notifier 'primary')
mc event add "${MC_ALIAS_HOT}/imagery" \
  arn:minio:sqs::primary:kafka \
  --event put \
  --prefix "sound/" || echo "[WARN] Failed to add sound/ rule"

# Rule 2: image/ prefix → topic image.new (via notifier 'images')
mc event add "${MC_ALIAS_HOT}/imagery" \
  arn:minio:sqs::images:kafka \
  --event put \
  --prefix "image/" || echo "[WARN] Failed to add image/ rule"

# Rule 3: telemetry bucket → sound.new
mc event add "${MC_ALIAS_HOT}/telemetry" \
  arn:minio:sqs::primary:kafka \
  --event put || echo "[WARN] Failed to add telemetry rule"

echo "[bootstrap] verifying event rules..."
mc event list "${MC_ALIAS_HOT}/imagery" || true
mc event list "${MC_ALIAS_HOT}/telemetry" || true

echo "[bootstrap] DONE."
SH

# --- Ensure init.sh has UNIX line endings ---
RUN apk add --no-cache dos2unix && dos2unix /entrypoint/init.sh

# ===== supervisord.conf =====
RUN cat > /etc/supervisord.conf <<'CONF'
[supervisord]
nodaemon=true
logfile=/var/log/supervisor/supervisord.log
[program:minio_hot]
command=/usr/local/bin/minio server --address %(ENV_HOT_ADDRESS)s --console-address %(ENV_HOT_CONSOLE)s /data/hot
stdout_logfile=/var/log/supervisor/minio_hot.log
stderr_logfile=/var/log/supervisor/minio_hot.err
autorestart=true
priority=10
[program:minio_cold]
command=/usr/local/bin/minio server --address %(ENV_COLD_ADDRESS)s --console-address %(ENV_COLD_CONSOLE)s /data/cold
stdout_logfile=/var/log/supervisor/minio_cold.log
stderr_logfile=/var/log/supervisor/minio_cold.err
autorestart=true
priority=10
[program:bootstrap]
command=/bin/bash -lc "/entrypoint/init.sh"
stdout_logfile=/var/log/supervisor/bootstrap.log
stderr_logfile=/var/log/supervisor/bootstrap.err
autorestart=false
startsecs=0
priority=20
CONF
EXPOSE 9000 9001 9100 9101
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]





















