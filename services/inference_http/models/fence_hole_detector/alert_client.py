import json
import os
import uuid
from datetime import datetime, timezone

from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError, NoBrokersAvailable

# --- Configuration (env-first) ---
_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
_TOPIC = os.getenv("ALERTS_TOPIC", "alerts")
_ALERT_TYPE = os.getenv("ALERT_TYPE", "fence_hole")

# You can tune these if you want faster failures during dev.
_PRODUCER_KW = dict(
    bootstrap_servers=_BOOTSTRAP,
    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    linger_ms=50,
    retries=5,
    request_timeout_ms=10_000,
    metadata_max_age_ms=15_000,
)

_admin = None
_producer = None


def _iso(ts: datetime | None) -> str:
    """Return RFC3339/ISO-8601 UTC string without microseconds (…Z)."""
    return (
        (ts or datetime.now(timezone.utc))
        .astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _get_admin() -> KafkaAdminClient:
    """Create a singleton admin client."""
    global _admin
    if _admin is None:
        _admin = KafkaAdminClient(bootstrap_servers=_BOOTSTRAP, request_timeout_ms=10_000)
    return _admin


def _ensure_topic(topic: str, num_partitions: int = 1, replication_factor: int = 1) -> None:
    """
    Idempotently create the topic if it doesn't exist.
    This is required because auto-create is disabled on the broker.
    """
    try:
        admin = _get_admin()
        new_topic = NewTopic(name=topic, num_partitions=num_partitions,
                             replication_factor=replication_factor)
        admin.create_topics([new_topic], validate_only=False)
    except TopicAlreadyExistsError:
        # OK: topic already present.
        return
    except NoBrokersAvailable as e:
        # Bubble up; the caller will log and continue the request flow.
        raise e
    except Exception:
        # For repeated concurrent creates we may see unknown errors from the broker;
        # treat them as non-fatal if the topic exists by the time we send.
        pass


def _get_producer() -> KafkaProducer:
    """Create a singleton producer."""
    global _producer
    if _producer is None:
        _producer = KafkaProducer(**_PRODUCER_KW)
    return _producer


def post_alert(
    *,
    device_id: str,
    started_at: datetime,
    confidence: float,
    image_url: str | None,
    area: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    severity: int | None = None,
    extra: dict | None = None,
) -> str:
    """
    Build and send an alert message to Kafka in the agreed schema.
    Returns the generated alert_id (UUID string).
    Raises if the broker is not reachable.
    """
    # Ensure topic exists (safe to call on every send).
    _ensure_topic(_TOPIC)

    alert_id = str(uuid.uuid4())
    payload = {
        # Required
        "alert_id": alert_id,
        "alert_type": _ALERT_TYPE,
        "device_id": device_id,
        "started_at": _iso(started_at),

        # Optional/metadata
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
        payload["meta"] = extra

    # Send
    producer = _get_producer()
    fut = producer.send(_TOPIC, payload)
    # Block until acknowledged (fail fast in dev)
    fut.get(timeout=10.0)
    producer.flush(timeout=5.0)

    return alert_id
