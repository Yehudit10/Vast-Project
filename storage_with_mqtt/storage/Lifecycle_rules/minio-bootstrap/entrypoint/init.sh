#!/bin/bash
set -euo pipefail

# === Wait for MinIO HOT ===
echo "Waiting for MinIO HOT..."
until curl -sf http://minio-hot:9000/minio/health/ready >/dev/null; do
  sleep 2
done

# === Wait for MinIO COLD ===
echo "Waiting for MinIO COLD..."
until curl -sf http://minio-cold:9000/minio/health/ready >/dev/null; do
  sleep 2
done

# === Configure aliases ===
echo "Configuring MinIO aliases..."
until mc alias set hot http://minio-hot:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  sleep 2
done
until mc alias set cold http://minio-cold:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  sleep 2
done

# === Create buckets ===
for BUCKET in "$BUCKET_IMAGERY" "$BUCKET_TELEMETRY"; do
  if ! mc ls hot | grep -q "$BUCKET"; then
    echo "Creating bucket: $BUCKET"
    mc mb hot/$BUCKET || true
  else
    echo "Bucket $BUCKET already exists."
  fi
done

# === Wait for Kafka broker ===
echo "Waiting for Kafka broker..."
until nc -z kafka 9092 >/dev/null 2>&1; do
  sleep 3
done

# === Wait for MinIO Kafka notifier (fully loaded) ===
echo "Waiting for all Kafka notifiers to load..."
until mc admin config get hot notify_kafka | grep -q "notify_kafka:primary" && \
      mc admin config get hot notify_kafka | grep -q "notify_kafka:images"; do
  echo "Kafka notifiers not ready yet... retrying..."
  sleep 3
done

# === Clean old event rules ===
mc event remove hot/$BUCKET_IMAGERY --force >/dev/null 2>&1 || true
mc event remove hot/$BUCKET_TELEMETRY --force >/dev/null 2>&1 || true

# === Add new Kafka event rules ===
echo "Adding new Kafka event rules..."
# Rule 1: sound/ prefix → topic sound.new (via notifier 'primary')
mc event add hot/$BUCKET_IMAGERY \
  arn:minio:sqs::primary:kafka \
  --event put \
  --prefix "sound/"

# Rule 2: image/ prefix → topic image.new (via notifier 'images')
mc event add hot/$BUCKET_IMAGERY \
  arn:minio:sqs::images:kafka \
  --event put \
  --prefix "image/"

# Rule 3: telemetry bucket → sound.new
mc event add hot/$BUCKET_TELEMETRY \
  arn:minio:sqs::primary:kafka \
  --event put

# === Verify ===
mc event list hot/$BUCKET_IMAGERY || true
mc event list hot/$BUCKET_TELEMETRY || true

tail -f /dev/null
