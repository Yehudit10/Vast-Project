#!/usr/bin/env bash
set -euo pipefail

# Kafka bootstrap used by admin tools inside the container
BOOTSTRAP="${BOOTSTRAP:-localhost:9092}"

# 7 days retention in milliseconds
RETENTION_DAYS="${RETENTION_DAYS:-7}"
RET_MS=$((RETENTION_DAYS*24*60*60*1000))

log() { echo "[topics] $*"; }

# Wait for Kafka to be ready (admin tools can list topics)
log "waiting for Kafka at $BOOTSTRAP ..."
for i in {1..60}; do
  if /opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server "$BOOTSTRAP" --list >/dev/null 2>&1; then
    log "Kafka is up."
    break
  fi
  sleep 2
  if [[ $i -eq 60 ]]; then
    log "ERROR: Kafka did not become ready in time."
    exit 1
  fi
done

# Required topics with 7-day retention
TOPICS=(
  dev-robot-alerts
  dev-robot-commands
  dev-robot-status
  dev-robot-telemetry-raw
  dev-robot-state
  dev-camera-security
)

# Idempotent creation with retention.ms
for T in "${TOPICS[@]}"; do
  /opt/bitnami/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists \
    --topic "$T" \
    --partitions 1 \
    --replication-factor 1 \
    --config "retention.ms=${RET_MS}"
done

log "✅ ensured topics with retention.ms=${RET_MS} (7 days)"
