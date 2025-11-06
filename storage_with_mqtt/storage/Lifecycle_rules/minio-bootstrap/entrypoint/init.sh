#!/usr/bin/env bash
set -euo pipefail

: "${MINIO_ROOT_USER:?Missing MINIO_ROOT_USER}"
: "${MINIO_ROOT_PASSWORD:?Missing MINIO_ROOT_PASSWORD}"
: "${MC_ALIAS_HOT:=hot}"
: "${MC_ALIAS_COLD:=cold}"
: "${HOT_ENDPOINT:=http://minio-hot:9000}"
: "${COLD_ENDPOINT:=http://minio-cold:9000}"

mc alias set "${MC_ALIAS_HOT}"  "${HOT_ENDPOINT}"  "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" || true
mc alias set "${MC_ALIAS_COLD}" "${COLD_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" || true

echo "[bootstrap] Checking HTTP availability..."
until curl -sf "${HOT_ENDPOINT}/minio/health/live"  >/dev/null; do sleep 1; done
until curl -sf "${COLD_ENDPOINT}/minio/health/live" >/dev/null; do sleep 1; done

echo "[bootstrap] Waiting for HOT (${HOT_ENDPOINT})..."
until mc ls "${MC_ALIAS_HOT}"  >/dev/null 2>&1; do sleep 2; done
echo "[bootstrap] Waiting for COLD (${COLD_ENDPOINT})..."
until mc ls "${MC_ALIAS_COLD}" >/dev/null 2>&1; do sleep 2; done

echo "[bootstrap] Creating buckets..."
mc mb "${MC_ALIAS_HOT}/imagery"   || true
mc mb "${MC_ALIAS_HOT}/sound" || true
mc mb "${MC_ALIAS_COLD}/imagery"   || true
mc mb "${MC_ALIAS_COLD}/sound" || true

echo "[bootstrap] Enabling versioning..."
mc version enable "${MC_ALIAS_HOT}/imagery"   || true
mc version enable "${MC_ALIAS_HOT}/sound" || true

echo "[bootstrap] Waiting for Kafka broker..."
until nc -z kafka 9092 >/dev/null 2>&1; do 
  echo "[bootstrap] Kafka not ready, retrying..."
  sleep 3
done
echo "[bootstrap] Kafka is accessible."

echo "[bootstrap] Configuring all Kafka notifiers..."


# Configure IMAGE notifiers
echo "[bootstrap] → aerial"
mc admin config set "${MC_ALIAS_HOT}" notify_kafka:aerial \
  brokers="kafka:9092" \
  topic="image.new.aerial"

echo "[bootstrap] → air"
mc admin config set "${MC_ALIAS_HOT}" notify_kafka:air \
  brokers="kafka:9092" \
  topic="image.new.air"

echo "[bootstrap] → fruits"
mc admin config set "${MC_ALIAS_HOT}" notify_kafka:fruits \
  brokers="kafka:9092" \
  topic="image.new.fruits"

echo "[bootstrap] → leaves"
mc admin config set "${MC_ALIAS_HOT}" notify_kafka:leaves \
  brokers="kafka:9092" \
  topic="image.new.leaves"

echo "[bootstrap] → ground"
mc admin config set "${MC_ALIAS_HOT}" notify_kafka:ground \
  brokers="kafka:9092" \
  topic="image.new.ground"

echo "[bootstrap] → field"
mc admin config set "${MC_ALIAS_HOT}" notify_kafka:field \
  brokers="kafka:9092" \
  topic="image.new.field"

# Configure SOUND notifiers
echo "[bootstrap] → plants"
mc admin config set "${MC_ALIAS_HOT}" notify_kafka:plants \
  brokers="kafka:9092" \
  topic="sound.new.plants"

echo "[bootstrap] → sounds"
mc admin config set "${MC_ALIAS_HOT}" notify_kafka:sounds \
  brokers="kafka:9092" \
  topic="sound.new.sounds"

echo "[bootstrap] ✅ All 7 notifiers configured"
echo "[bootstrap] ⚠️ Restarting MinIO to apply notifier changes..."
mc admin service restart "${MC_ALIAS_HOT}" --json || true

# Wait for MinIO restart with retry instead of fixed sleep
echo "[bootstrap] Waiting for MinIO to come back online (with retries)..."
max_retries=${MAX_MINIO_RETRIES:-60}       # Default: 60 attempts
retry_interval=${MINIO_RETRY_INTERVAL:-5} # Default: 5 seconds
i=0
until mc ls "${MC_ALIAS_HOT}" >/dev/null 2>&1; do
  i=$((i+1))
  if [ "$i" -ge "$max_retries" ]; then
    echo "[bootstrap] ERROR: MinIO did not become ready after $((max_retries * retry_interval)) seconds"
    break
  fi
  echo "[bootstrap] MinIO not ready, attempt $i/$max_retries (waiting ${retry_interval}s)..."
  sleep "$retry_interval"
done

if mc ls "${MC_ALIAS_HOT}" >/dev/null 2>&1; then
  echo "[bootstrap] ✅ MinIO is back online"
else
  echo "[bootstrap] ⚠️ Continuing even though MinIO did not fully recover (check logs)"
fi

echo "[bootstrap] Verifying Kafka notifiers..."
mc admin config get "${MC_ALIAS_HOT}" notify_kafka

echo "[bootstrap] Ensuring remote tiers exist in HOT..."
if ! mc ilm tier ls "${MC_ALIAS_HOT}" --json | grep -q '"Name":"COLD_IMAGERY"'; then
  mc ilm tier add s3 "${MC_ALIAS_HOT}" COLD_IMAGERY \
    --endpoint   "${COLD_ENDPOINT}" \
    --access-key "${MINIO_ROOT_USER}" \
    --secret-key "${MINIO_ROOT_PASSWORD}" \
    --bucket imagery \
    --region us-east-1 || true
fi

if ! mc ilm tier ls "${MC_ALIAS_HOT}" --json | grep -q '"Name":"COLD_SOUND"'; then
  mc ilm tier add s3 "${MC_ALIAS_HOT}" COLD_SOUND \
    --endpoint   "${COLD_ENDPOINT}" \
    --access-key "${MINIO_ROOT_USER}" \
    --secret-key "${MINIO_ROOT_PASSWORD}" \
    --bucket sound \
    --region us-east-1 || true
fi

echo "[bootstrap] Applying lifecycle policies..."
mc ilm rule rm "${MC_ALIAS_HOT}/imagery" --all --force || true
if [ -s "/config/lifecycle-imagery.json" ]; then
  mc ilm import "${MC_ALIAS_HOT}/imagery" < "/config/lifecycle-imagery.json" || true
else
  mc ilm rule add "${MC_ALIAS_HOT}/imagery" \
    --transition-days 7 --transition-tier COLD_IMAGERY || true
fi

mc ilm rule rm "${MC_ALIAS_HOT}/sound" --all --force || true
if [ -s "/config/lifecycle-sound.json" ]; then
  mc ilm import "${MC_ALIAS_HOT}/sound" < "/config/lifecycle-sound.json" || true
else
  mc ilm rule add "${MC_ALIAS_HOT}/sound" \
    --transition-days 7 --transition-tier COLD_SOUND || true
fi

echo "[bootstrap] Removing old event rules..."
mc event remove "${MC_ALIAS_HOT}/imagery" --force >/dev/null 2>&1 || true
mc event remove "${MC_ALIAS_HOT}/sound" --force >/dev/null 2>&1 || true

sleep 3
echo "[bootstrap] Adding Kafka event rules for IMAGERY..."
mc event add "${MC_ALIAS_HOT}/imagery" \
  arn:minio:sqs::aerial:kafka \
  --event put \
  --prefix "aerial/"

mc event add "${MC_ALIAS_HOT}/imagery" \
  arn:minio:sqs::aerial:kafka \
  --event put \
  --prefix "image/camera-air/"

mc event add "${MC_ALIAS_HOT}/imagery" \
  arn:minio:sqs::fruits:kafka \
  --event put \
  --prefix "fruits/"

mc event add "${MC_ALIAS_HOT}/imagery" \
  arn:minio:sqs::leaves:kafka \
  --event put \
  --prefix "leaves/"

mc event add "${MC_ALIAS_HOT}/imagery" \
  arn:minio:sqs::ground:kafka \
  --event put \
  --prefix "ground/"

mc event add "${MC_ALIAS_HOT}/imagery" \
  arn:minio:sqs::field:kafka \
  --event put \
  --prefix "field/"

echo "[bootstrap] Adding Kafka event rules for SOUND..."
mc event add "${MC_ALIAS_HOT}/sound" \
  arn:minio:sqs::plants:kafka \
  --event put \
  --prefix "plants/"

mc event add "${MC_ALIAS_HOT}/sound" \
  arn:minio:sqs::sounds:kafka \
  --event put \
  --prefix "sounds/"

echo "[bootstrap] Validating event rules..."
mc event list "${MC_ALIAS_HOT}/imagery" || true
mc event list "${MC_ALIAS_HOT}/sound" || true
echo "[bootstrap] ✅ Done."
echo "[bootstrap] Keeping container alive..."
tail -f /dev/null
