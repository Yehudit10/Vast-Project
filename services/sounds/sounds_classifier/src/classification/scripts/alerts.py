import json
import time
import logging
from typing import Optional, Dict, Any
from confluent_kafka import Producer, KafkaException
import uuid
from datetime import datetime, timezone

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

def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strtime("%Y-%m-%dT%H:%M:%SZ")

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

# ---- Structured alert with strict required fields ----
REQUIRED_FIELDS = ("alert_id", "alert_type", "device_id", "started_at")

def send_structured_alert(
    *,
    brokers: str,
    topic: str = "alerts",
    alert_type: str,
    device_id: str,
    started_at: str,
    ended_at: Optional[str] = None,
    confidence: Optional[float] = None,
    severity: Optional[int] = None,
    area: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    image_url: Optional[str] = None,
    vod: Optional[str] = None,
    hls: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    alert_id: Optional[str] = None,
    message_key: Optional[str] = None,
) -> bool:
    """
    Send alert JSON to Kafka in the required schema.
    Required: alert_id, alert_type, device_id, started_at (ISO-8601 Z).
    Optional fields are included ONLY if explicitly provided (no defaults/guesses).
    """
    payload: Dict[str, Any] = {
        "alert_id": alert_id or str(uuid.uuid4()),
        "alert_type": alert_type,
        "device_id": device_id,
        "started_at": started_at,
    }

    # Append optional fields IFF provided (no guessing)
    if ended_at: payload["ended_at"] = ended_at
    if confidence is not None: payload["confidence"] = float(confidence)
    if severity is not None: payload["severity"] = int(severity)
    if area: payload["area"] = area
    if lat is not None: payload["lat"] = float(lat)
    if lon is not None: payload["lon"] = float(lon)
    if image_url: payload["image_url"] = image_url
    if vod: payload["vod"] = vod
    if hls: payload["hls"] = hls
    if meta is not None: payload["meta"] = meta

    missing = [f for f in REQUIRED_FIELDS if f not in payload or payload[f] in (None, "")]
    if missing:
        LOGGER.error("Structured alert missing required fields: %s", missing)
        return False

    try:
        p = _get_producer(brokers)
        p.produce(
            topic=topic,
            value=json.dumps(payload).encode("utf-8"),
            key=(message_key.encode("utf-8") if isinstance(message_key, str) else None),
            callback=_delivery_report
        )
        p.poll(0)
        return True
    except KafkaException as e:
        LOGGER.error("Kafka exception while producing structured alert: %s", e)
        return False
    except Exception as e:
        LOGGER.error("Kafka produce error (structured alert): %s", e)
        return False