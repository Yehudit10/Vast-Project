#!/usr/bin/env bash
set -euo pipefail

# Bootstrap (???? ????? ?? BOOTSTRAP=.. ???? ?????)
BOOTSTRAP="${BOOTSTRAP:-localhost:9092}"

# Retention (????? ???? 7 ????)
RETENTION_DAYS="${RETENTION_DAYS:-7}"
RETENTION_MS=$((RETENTION_DAYS*24*60*60*1000))

# ??????? ?? ????? 7 ????
TOPICS=(dev.robot.alerts dev.robot.commands dev.robot.status dev.robot.telemetry.raw)

for T in "${TOPICS[@]}"; do
  /opt/bitnami/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists \
    --topic "$T" --partitions 1 --replication-factor 1 \
    --config "retention.ms=${RETENTION_MS}"
done

# ????? state: compact+delete + 7 ????
STATE_TOPIC=dev.robot.state
/opt/bitnami/kafka/bin/kafka-topics.sh \
  --bootstrap-server "$BOOTSTRAP" \
  --create --if-not-exists \
  --topic "$STATE_TOPIC" --partitions 1 --replication-factor 1

/opt/bitnami/kafka/bin/kafka-configs.sh \
  --bootstrap-server "$BOOTSTRAP" \
  --alter --topic "$STATE_TOPIC" \
  --add-config "retention.ms=${RETENTION_MS},cleanup.policy=[compact,delete]"

echo "Topics ensured on $BOOTSTRAP with retention=${RETENTION_MS}ms"
