import json
import time
import logging
from typing import Optional, Dict, Any

from confluent_kafka import Producer, KafkaException

LOGGER = logging.getLogger("audio_cls.alerts")
if not LOGGER.handlers:
    # Minimal console handler if none configured by the app
    h = logging.StreamHandler()
    fmt = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    h.setFormatter(fmt)
    LOGGER.addHandler(h)
LOGGER.setLevel(logging.INFO)

# Cache one Producer per brokers string
_producer_cache: dict[str, Producer] = {}

def _get_producer(brokers: str) -> Producer:
    """
    Lazily create and cache a Kafka Producer for the given brokers string.
    Do NOT load env here; configuration is passed by the caller (service).
    """
    p = _producer_cache.get(brokers)
    if p is not None:
        return p

    conf = {
        "bootstrap.servers": brokers,
        "queue.buffering.max.ms": 5,     # small batching for low latency
        "message.timeout.ms": 5000,      # fail fast
        "socket.keepalive.enable": True,
        "api.version.request": True,
    }
    try:
        p = Producer(conf)
    except KafkaException as e:
        LOGGER.error("Failed to initialize Kafka producer (brokers=%s): %s", brokers, e)
        raise
    _producer_cache[brokers] = p
    return p

def _delivery_report(err, msg):
    if err is not None:
        LOGGER.warning("Kafka delivery failed: %s", err)
    else:
        LOGGER.info(
            "Kafka delivered: topic=%s partition=%s offset=%s",
            msg.topic(), msg.partition(), msg.offset()
        )

def send_alert(
    *,
    brokers: str,
    topic: str,
    label: str,
    probs: Dict[str, float],
    meta: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send a JSON alert to Kafka. Returns True if enqueued+delivered (within flush timeout),
    False on immediate failure. Delivery problems are logged via _delivery_report.
    """
    payload = {
        "label": label,
        "probs": probs,
        "meta": meta or {},
        "ts": int(time.time() * 1000),
    }
    try:
        p = _get_producer(brokers)
        p.produce(topic=topic, value=json.dumps(payload).encode("utf-8"), callback=_delivery_report)
        # Serve delivery callbacks; flush returns number of undelivered messages (0 == success)
        p.poll(0)
        # undelivered = p.flush(5)
        # if undelivered != 0:
        #     LOGGER.warning("Kafka flush returned %s undelivered message(s)", undelivered)
        #     return False
        return True
    except KafkaException as e:
        LOGGER.error("Kafka exception while producing: %s", e)
        return False
    except BufferError as e:
        LOGGER.error("Kafka local queue full: %s", e)
        return False
    except Exception as e:
        LOGGER.error("Kafka produce error: %s", e)
        return False

# ---- Backwards compatibility shim ----
def send_kafka_alert(file_path: str, label: str, prob: float) -> bool:
    """
    Legacy helper kept for backward compatibility. Reads brokers/topic from env
    ONLY if caller insists on using this function. Prefer send_alert(...).
    """
    import os  # local import to avoid env dependency on module load
    brokers = os.getenv("KAFKA_BROKERS") or os.getenv("KAFKA_BROKER", "localhost:9092")
    topic = os.getenv("ALERTS_TOPIC") or os.getenv("KAFKA_ALERTS_TOPIC", "alerts")

    payload_probs = {label: float(prob)}
    meta = {"file_path": file_path, "source": "legacy_send_kafka_alert"}

    return send_alert(
        brokers=brokers,
        topic=topic,
        label=label,
        probs=payload_probs,
        meta=meta,
    )
