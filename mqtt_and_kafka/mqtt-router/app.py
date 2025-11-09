import os
import re
import json
import signal
import sys
from typing import Optional

import paho.mqtt.client as mqtt
from confluent_kafka import Producer, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC_FILTER = os.getenv("MQTT_TOPIC_FILTER", "mqtt/#")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
KAFKA_CLIENT_ID = os.getenv("KAFKA_CLIENT_ID", "mqtt-router")
CREATE_TOPICS = os.getenv("CREATE_TOPICS", "true").lower() == "true"
DEFAULT_PARTITIONS = int(os.getenv("DEFAULT_PARTITIONS", "1"))
DEFAULT_REPLICATION = int(os.getenv("DEFAULT_REPLICATION", "1"))

# mqtt/<team>/<kind>/<name>  ->  <team>.<kind>.<name>
ROUTE_REGEX = re.compile(r"^mqtt/([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+)$")
VALID_CHARS = re.compile(r'[^A-Za-z0-9._-]')

p = Producer({
    "bootstrap.servers": KAFKA_BOOTSTRAP,
    "client.id": KAFKA_CLIENT_ID,
})

admin = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP})

def ensure_topic(topic: str):
    if not CREATE_TOPICS:
        return
    # Try to create topic; ignore if exists
    new_topic = NewTopic(topic, num_partitions=DEFAULT_PARTITIONS, replication_factor=DEFAULT_REPLICATION)
    fs = admin.create_topics([new_topic])
    f = fs.get(topic)
    try:
        f.result()
        print(f"[router] Created topic: {topic}")
    except Exception as e:
        # If already exists or concurrent create, ignore
        msg = str(e)
        if "TopicExistsError" in msg or "TOPIC_ALREADY_EXISTS" in msg:
            return
        # Some clusters return generic error when exists; we can ignore safe
        if "already exists" in msg.lower():
            return
        print(f"[router] create_topics warning for {topic}: {e}")

def delivery_report(err, msg):
    if err is not None:
        print(f"[router] Delivery failed for {msg.topic()}: {err}")
    else:
        print(f"[router] Delivered to {msg.topic()} [partition {msg.partition()} offset {msg.offset()}]")

def map_mqtt_to_kafka_topic(mqtt_topic: str) -> str | None:
    # Must start with "mqtt/"
    prefix = "mqtt/"
    if not mqtt_topic.startswith(prefix):
        return None

    # Take everything after "mqtt/", strip any leading/trailing slashes
    tail = mqtt_topic[len(prefix):].strip("/")
    if not tail:
        # nothing after mqtt/
        return None

    # Collapse multiple slashes and join by dot
    parts = [seg for seg in tail.split("/") if seg]  # skip empty segments from '//' occurrences
    dotted = ".".join(parts)

    # Sanitize invalid characters for Kafka topic names
    dotted = VALID_CHARS.sub("_", dotted)

    # Enforce Kafka max length (optional: truncate or hash)
    if len(dotted) > 249:
        dotted = dotted[:249]  # or replace with a hashed version if you prefer

    return dotted if dotted else None

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[router] Connected to MQTT {MQTT_HOST}:{MQTT_PORT}, subscribing to {MQTT_TOPIC_FILTER}")
        client.subscribe(MQTT_TOPIC_FILTER, qos=0)
    else:
        print(f"[router] MQTT connect failed: rc={rc}")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload  # bytes as-is
    dst = map_mqtt_to_kafka_topic(topic)
    if dst is None:
        print(f"[router] Skipping topic (no match): {topic}")
        return
    try:
        ensure_topic(dst)
        p.produce(dst, value=payload, on_delivery=delivery_report)
        p.poll(0)
    except KafkaException as e:
        print(f"[router] Kafka produce error: {e}")

def main():
    client = mqtt.Client(client_id="mqtt-router", protocol=mqtt.MQTTv5)
    if MQTT_USERNAME or MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message

    def handle_sigterm(signum, frame):
        print("[router] SIGTERM received, flushing producer...")
        p.flush(10)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_forever()

if __name__ == "__main__":
    main()
