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

TOPICS=(
  dev-robot-alerts
  dev-robot-commands
  dev-robot-status
  dev-robot-telemetry-raw
  dev-robot-state

  dev-camera-security
  sensor-telemetry
  sensor-anomalies
  dev-robot-telemetry-anomalies

  sensor_anomalies
  sensor_zone_stats
  dev-robot-telemetry-anomalies
  summaries.5m
  irrigation.control
  irrigation.control.dlq
  sound.new
  image.new
  aerial_images_metadata
  dev-security-images-keys
  alerts

  aerial_image_object_detections
  aerial_image_anomaly_detections
  aerial_image_segmentation
  aerial_images_complete_metadata
  
  # --- imagery (MinIO -> Kafka) ---
  image.new.aerial
  image_new_aerial_connections
  image.new.fruits
  image.new.leaves
  image.new.ground
  image.new.field
  image.new.security
  image_new_security_connections
  
  # --- sound(sound) (MinIO -> Kafka) ---
  sound.new.plants
  sound.new.sounds
  sounds_ultra_metadata
  sounds_metadata
  sound_new_plants_connections
  sound_new_sounds_connections

  inference.dispatched.sounds
  dlq.inference.http
  event_logs_sensors
  sensors
  sensors_anomalies_modal
  aerial_images_keys
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
