# alert_client.py
import json
import os
import uuid
from datetime import datetime, timezone
from kafka import KafkaProducer

_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
_TOPIC = os.getenv("ALERTS_TOPIC", "alerts")
_ALERT_TYPE = os.getenv("ALERT_TYPE", "fence_hole_detected")

_producer = None

def _get_producer():
    global _producer
    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            linger_ms=50,
            retries=5,
        )
    return _producer

def _iso(ts: datetime | None) -> str:
    return (ts or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def post_alert(*, device_id: str, started_at: datetime, confidence: float,
               image_url: str | None, area: str | None = None,
               lat: float | None = None, lon: float | None = None,
               severity: int | None = None, extra: dict | None = None) -> str:
    """
    בונה ומפרסם הודעת התראה לטופיק Kafka בהתאם לסכימה שסיפקת.
    מחזיר alert_id.
    """
    alert_id = str(uuid.uuid4())
    payload = {
        # Required
        "alert_id": alert_id,
        "alert_type": _ALERT_TYPE,
        "device_id": device_id,
        "started_at": _iso(started_at),

        # Optional
        "confidence": round(float(confidence), 3),
    }
    if severity is not None:
        payload["severity"] = int(severity)
    if area:
        payload["area"] = area
    if lat is not None:
        payload["lat"] = float(lat)
    if lon is not None:
        payload["lon"] = float(lon)
    if image_url:
        payload["image_url"] = image_url
    if extra:
        payload["meta"] = extra  # שדה meta חופשי

    producer = _get_producer()
    producer.send(_TOPIC, payload)
    producer.flush()
    return alert_id
