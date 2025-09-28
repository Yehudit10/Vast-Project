import os
import json
import logging
from confluent_kafka import Producer, KafkaException
from dotenv import load_dotenv, find_dotenv
from openai import timeout

# Load .env file
dotenv_path = find_dotenv(usecwd=True)
load_dotenv(dotenv_path, override=True)

# Kafka configuration from env
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_ALERTS_TOPIC", "alerts")

print("================================================")
print(KAFKA_BROKER)
print(KAFKA_TOPIC)
print("================================================")
LOGGER = logging.getLogger("audio_cls.alerts")
LOGGER.setLevel(logging.INFO)

# Try to create Kafka producer once
try:
    KAFKA_PRODUCER = Producer({'bootstrap.servers': KAFKA_BROKER})
    LOGGER.info("Kafka producer initialized (broker=%s, topic=%s)", KAFKA_BROKER, KAFKA_TOPIC)
except KafkaException as e:
    KAFKA_PRODUCER = None
    LOGGER.warning("Failed to initialize Kafka producer: %s", e)


def send_kafka_alert(file_path: str, label: str, prob: float):
    """
    Send alert to Kafka if producer is available. Logs warning if Kafka is unavailable.
    """
    if KAFKA_PRODUCER is None:
        LOGGER.warning("Kafka unavailable, cannot send alert for %s -> %s", file_path, label)
        return

    msg = {"file_path": file_path, "label": label, "probability": prob}

    def delivery_report(err, delivered_msg):
        if err is not None:
            LOGGER.warning("Failed to deliver Kafka message for %s -> %s: %s", file_path, label, err)
        else:
            LOGGER.info("Kafka alert sent successfully for %s -> %s (%.4f)", file_path, label, prob)

    try:
        KAFKA_PRODUCER.produce(KAFKA_TOPIC, json.dumps(msg), callback=delivery_report)
        KAFKA_PRODUCER.flush(timeout=5)
    except KafkaException as e:
        LOGGER.warning("Exception during Kafka produce for %s -> %s: %s", file_path, label, e)
