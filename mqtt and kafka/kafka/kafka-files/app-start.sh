#!/usr/bin/env bash
set -euo pipefail

# --------
# app-start.sh
# Purpose:
# 1) Start Kafka (using Bitnami entrypoint/run scripts)
# 2) Wait until the broker is ready
# 3) Run create-topics.sh (7-day retention)
# 4) Run smoke-test.sh (kcat produce/consume)
# 5) Keep the container alive while Kafka runs
# --------

# Internal bootstrap for in-container admin/tools
BOOTSTRAP="${BOOTSTRAP:-127.0.0.1:9092}"

# Start Kafka in background using Bitnami's scripts
/opt/bitnami/scripts/kafka/entrypoint.sh /opt/bitnami/scripts/kafka/run.sh &
KAFKA_PID=$!

echo "[entry] Kafka starting (pid=${KAFKA_PID}) ... waiting for readiness"

# Wait until kafkatools can talk to the broker
for i in {1..120}; do
  if /opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server "${BOOTSTRAP}" --list >/dev/null 2>&1; then
    echo "[entry] Kafka is ready."
    break
  fi
  sleep 2
  if [[ $i -eq 120 ]]; then
    echo "[entry] ERROR: Kafka did not become ready in time." >&2
    kill ${KAFKA_PID} || true
    wait ${KAFKA_PID} || true
    exit 1
  fi
done

# Create required topics (idempotent)
echo "[entry] running create-topics.sh ..."
RETENTION_DAYS="${RETENTION_DAYS:-7}" BOOTSTRAP="${BOOTSTRAP}" /opt/bitnami/create-topics.sh

# Smoke test (kcat one-shot produce+consume)
echo "[entry] running smoke-test.sh ..."
BOOTSTRAP="${BOOTSTRAP}" /opt/bitnami/smoke-test.sh || {
  echo "[entry] WARNING: smoke test failed (continuing so Kafka remains available)" >&2
}

# Stay attached to Kafka process
wait ${KAFKA_PID}
