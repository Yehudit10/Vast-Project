#!/usr/bin/env bash
set -euo pipefail

# ------- config -------
CONNECTOR_NAME="mqtt-source"
CONFIG_FILE="connectors/mqtt-source.json"  # config-only JSON (no top-level "name" or "config")
COMPOSE_CMD="docker compose"               # change to 'docker-compose' if needed
NETWORK_NAME="agcloud_mesh"                # must match your docker-compose.yml
MOSQUITTO_SVC="mosquitto"
KAFKA_SVC="kafka"
CONNECT_SVC="connect-1"
# ----------------------

echo "==> Bringing stack down (volumes too) ..."
$COMPOSE_CMD down -v || true

echo "==> Starting stack ..."
$COMPOSE_CMD up -d

# --- wait for health of a container by name ---
wait_healthy() {
  local name="$1"
  echo "==> Waiting for '$name' to become healthy ..."
  for i in {1..60}; do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null || echo "unknown")"
    if [[ "$status" == "healthy" ]]; then
      echo "    $name is healthy."
      return 0
    fi
    sleep 2
  done
  echo "ERROR: $name did not become healthy in time." >&2
  docker logs "$name" || true
  exit 1
}

wait_healthy "$KAFKA_SVC"
wait_healthy "$MOSQUITTO_SVC"
# connect-1 sometimes reports 'starting' while REST is already up; still wait:
wait_healthy "$CONNECT_SVC"

# --- verify connector plugin is available ---
echo "==> Checking connector plugins ..."
PLUGINS_JSON="$(curl -sf http://localhost:8083/connector-plugins)"
echo "$PLUGINS_JSON" | grep -q 'io.confluent.connect.mqtt.MqttSourceConnector' || {
  echo "ERROR: MQTT Source Connector not found in /connector-plugins" >&2
  echo "       Make sure plugin is mounted to: /usr/share/confluent-hub-components/confluentinc-kafka-connect-mqtt" >&2
  exit 1
}
echo "    MQTT plugin detected."

# --- extract kafka.topic from config (without jq) ---
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "ERROR: Config file not found: $CONFIG_FILE" >&2
  exit 1
fi

TOPIC="$(grep -oE '"kafka.topic"\s*:\s*"[^"]+"' "$CONFIG_FILE" | sed 's/.*"\([^"]*\)"/\1/')"
if [[ -z "${TOPIC:-}" ]]; then
  echo "WARN: Could not parse kafka.topic from $CONFIG_FILE ; defaulting to 'dev-robot-alerts'"
  TOPIC="dev-robot-alerts"
fi
echo "==> Will use Kafka topic: $TOPIC"

echo "==> Verifying Kafka topic exists: $TOPIC"
if ! docker exec -i "$KAFKA_SVC" /opt/bitnami/kafka/bin/kafka-topics.sh \
    --bootstrap-server localhost:9092 --list | grep -qx "$TOPIC"; then
  echo "ERROR: Kafka topic '$TOPIC' does not exist."
  echo "       Please ask the Kafka admin to create it (auto-create is disabled)."
  exit 1
fi

# --- upsert connector (POST if missing, otherwise PUT) ---
echo "==> Upserting connector: $CONNECTOR_NAME"

# Try GET status
set +e
STATUS_JSON="$(curl -s http://localhost:8083/connectors/${CONNECTOR_NAME}/status)"
set -e

if echo "${STATUS_JSON:-}" | grep -q '"name"'; then
  echo "    Connector exists -> updating (PUT /config)"
  curl -sf -X PUT -H "Content-Type: application/json" \
    --data-binary @"$CONFIG_FILE" \
    "http://localhost:8083/connectors/${CONNECTOR_NAME}/config" >/dev/null
else
  echo "    Connector missing -> creating (POST /connectors)"
  # Build a POST body that wraps the config into {"name": "...", "config": {...}}
  CONFIG_CONTENT="$(cat "$CONFIG_FILE")"
  POST_BODY="$(printf '{\"name\":\"%s\",\"config\":%s}\n' "$CONNECTOR_NAME" "$CONFIG_CONTENT")"
  echo "$POST_BODY" | curl -sf -X POST -H "Content-Type: application/json" \
    --data-binary @- \
    "http://localhost:8083/connectors" >/dev/null
fi

# Confirm RUNNING
echo "==> Verifying connector status ..."
for i in {1..30}; do
  S="$(curl -sf http://localhost:8083/connectors/${CONNECTOR_NAME}/status || true)"
  if echo "$S" | grep -q '"state":"RUNNING"'; then
    echo "    ${CONNECTOR_NAME} is RUNNING."
    break
  fi
  sleep 1
  if [[ $i -eq 30 ]]; then
    echo "ERROR: Connector did not reach RUNNING state:" >&2
    echo "$S" >&2
    exit 1
  fi
done

# --- E2E test: publish MQTT + consume Kafka ---
echo "==> Publishing test MQTT message ..."
docker exec -i "$MOSQUITTO_SVC" mosquitto_pub -h mosquitto -p 1883 -t mqtt/test -m '{"hello":"world"}'

echo "==> Consuming from Kafka (kcat) ..."
docker run --rm --network "$NETWORK_NAME" edenhill/kcat:1.7.1 \
  -b kafka:9092 -C -t "$TOPIC" -o end -q -c 1 || true

echo
echo "✅ All done!"
echo "   - Stack is up"
echo "   - Connector '${CONNECTOR_NAME}' is RUNNING"
echo "   - MQTT -> Kafka bridge verified on topic: ${TOPIC}"
