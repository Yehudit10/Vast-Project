#!/bin/sh
set -e

echo "🪄 Waiting for MinIO to be ready..."
until curl -s http://minio-hot:9000/minio/health/ready >/dev/null; do
  sleep 2
done

echo "✅ MinIO is ready. Configuring bucket events..."

mc alias set local http://minio-hot:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

if ! mc ls local | grep -q "mybucket"; then
  mc mb local/mybucket
fi

mc event add local/mybucket arn:minio:sqs::primary:kafka_primary --event put --prefix "sound/"
mc event add local/mybucket arn:minio:sqs::primary:kafka_images --event put --prefix "image/"

echo "Event configuration completed."
