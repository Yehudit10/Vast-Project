import os
import re
import signal
import sys
from typing import Optional

import paho.mqtt.client as mqtt
from confluent_kafka import Producer, KafkaException, KafkaError
from confluent_kafka.admin import AdminClient, NewTopic

# ---------- Env ----------
MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC_FILTER = os.getenv("MQTT_TOPIC_FILTER", "mqtt/#")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
KAFKA_CLIENT_ID = os.getenv("KAFKA_CLIENT_ID", "mqtt-router")
CREATE_TOPICS = os.getenv("CREATE_TOPICS", "false").lower() == "true"
DEFAULT_PARTITIONS = int(os.getenv("DEFAULT_PARTITIONS", "1"))
DEFAULT_REPLICATION = int(os.getenv("DEFAULT_REPLICATION", "1"))

# Optional security (set via env if needed)
KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "")  # e.g. "SASL_PLAINTEXT", "SASL_SSL", "SSL"
KAFKA_SASL_MECHANISM = os.getenv("KAFKA_SASL_MECHANISM", "")        # e.g. "PLAIN"
KAFKA_SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME", "")
KAFKA_SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD", "")

# ---------- Topic mapping ----------
# Allow arbitrary depth after "mqtt/" → replace "/" with "."
VALID_CHARS = re.compile(r'[^A-Za-z0-9._-]')

def map_mqtt_to_kafka_topic(mqtt_topic: str) -> Optional[str]:
    prefix = "mqtt/"
    if not mqtt_topic.startswith(prefix):
        return None
    tail = mqtt_topic[len(prefix):].strip("/")
    if not tail:
        return None
    parts = [seg for seg in tail.split("/") if seg]
    dotted = ".".join(parts)
    dotted = VALID_CHARS.sub("_", dotted)
    return dotted[:249] if dotted else None

# ---------- Kafka clients ----------
producer_conf = {
    "bootstrap.servers": KAFKA_BOOTSTRAP,
    "client.id": KAFKA_CLIENT_ID,

    # Strong delivery semantics
    "acks": "all",
    "enable.idempotence": True,

    # Throughput tuning
    "compression.type": os.getenv("KAFKA_COMPRESSION", "lz4"),
    "linger.ms": int(os.getenv("KAFKA_LINGER_MS", "5")),
    "batch.size": int(os.getenv("KAFKA_BATCH_SIZE", str(64 * 1024))),  # bytes

    # Resilience
    "socket.keepalive.enable": True,
    "delivery.timeout.ms": int(os.getenv("KAFKA_DELIVERY_TIMEOUT_MS", "120000")),
    "request.timeout.ms": int(os.getenv("KAFKA_REQUEST_TIMEOUT_MS", "30000")),
}

# Optional security
if KAFKA_SECURITY_PROTOCOL:
    producer_conf["security.protocol"] = KAFKA_SECURITY_PROTOCOL
if KAFKA_SASL_MECHANISM:
    producer_conf["sasl.mechanism"] = KAFKA_SASL_MECHANISM
if KAFKA_SASL_USERNAME:
    producer_conf["sasl.username"] = KAFKA_SASL_USERNAME
if KAFKA_SASL_PASSWORD:
    producer_conf["sasl.password"] = KAFKA_SASL_PASSWORD

p = Producer(producer_conf)
admin = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP})  # kept for CREATE_TOPICS toggle

def ensure_topic(topic: str):
    if not CREATE_TOPICS:
        return
    try:
        fs = admin.create_topics([NewTopic(topic, num_partitions=DEFAULT_PARTITIONS,
                                           replication_factor=DEFAULT_REPLICATION)])
        fs[topic].result()
        print(f"[router] Created topic: {topic}", flush=True)
    except Exception as e:
        msg = str(e)
        if "exists" in msg.lower() or "TopicExistsError" in msg or "TOPIC_ALREADY_EXISTS" in msg:
            return
        print(f"[router] create_topics warning for {topic}: {e}", flush=True)

def delivery_report(err, msg):
    if err is not None:
        print(f"[router] Delivery failed for {msg.topic()}: {err}", flush=True)
    else:
        print(f"[router] Delivered to {msg.topic()} [partition {msg.partition()} offset {msg.offset()}]", flush=True)

# ---------- MQTT callbacks ----------
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[router] Connected MQTT {MQTT_HOST}:{MQTT_PORT}, subscribe: {MQTT_TOPIC_FILTER}", flush=True)
        client.subscribe(MQTT_TOPIC_FILTER, qos=0)
    else:
        print(f"[router] MQTT connect failed: rc={rc}", flush=True)

def on_message(client, userdata, msg):
    src = msg.topic
    dst = map_mqtt_to_kafka_topic(src)
    if not dst:
        print(f"[router] Skipping topic (no match): {src}", flush=True)
        return
    try:
        ensure_topic(dst)
        p.produce(dst, value=msg.payload, on_delivery=delivery_report)
        # Poll to serve delivery callbacks; small 0 keeps loop snappy
        p.poll(0)
    except KafkaException as e:
        # Helpful message when topics are not pre-created
        kafka_err = e.args[0] if e.args else None
        if isinstance(kafka_err, KafkaError) and kafka_err.code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
            print(f"[router] ERROR UnknownTopicOrPartition for '{dst}'. "
                  f"CREATE_TOPICS=false → please pre-create this topic.", flush=True)
        else:
            print(f"[router] Kafka produce error: {e}", flush=True)

# ---------- Main ----------
def main():
    client = mqtt.Client(client_id="mqtt-router", protocol=mqtt.MQTTv5)
    if MQTT_USERNAME or MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # Gentle reconnect backoff
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    client.on_connect = on_connect
    client.on_message = on_message

    def handle_sigterm(signum, frame):
        print("[router] SIGTERM received, flushing producer...", flush=True)
        p.flush(10)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    print(f"[router] Boot: MQTT={MQTT_HOST}:{MQTT_PORT}  Kafka={KAFKA_BOOTSTRAP}  "
          f"CREATE_TOPICS={CREATE_TOPICS}", flush=True)
    client.loop_forever()

if __name__ == "__main__":
    main()
