import os
import json
from datetime import datetime
from typing import Any, Dict, Optional

from kafka import KafkaProducer
from core.types import Alert
from config.settings import settings


# Convert Alert dataclass to a stable dict for JSON serialization and downstream consumers.
def _alert_to_dict(alert: Alert) -> Dict[str, Any]:
    """
    Convert Alert to an ordered, serialization-friendly dict.
    Suitable for downstream consumers (DB / API / BI).
    """
    details: Dict[str, Any] = getattr(alert, "details", {}) or {}

    def iso(dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None

    d = {
        "issue_type": getattr(alert, "issue_type", None),
        "device_id": getattr(alert, "device_id", None),
        "severity": getattr(alert, "severity", None),
        "start_ts": iso(getattr(alert, "start_ts", None)),
        "details": details,
    }

    end_ts = getattr(alert, "end_ts", None)
    if end_ts is not None:
        d["end_ts"] = iso(end_ts)

    return d




# Kafka writer: send Alert objects as JSON value-only messages.
# Lazy-initialize producer to avoid early network/socket creation.
class KafkaWriter:
    """
    Write Alerts to Kafka as JSON (value-only).
    Defaults:
      - topic from OUT_TOPIC env or 'dev-robot-telemetry-raw'
      - brokers from KAFKA_BROKERS env or 'kafka:9092'
    """
    def __init__(
        self,
        topic: str | None = None,
        brokers: str | None = None,
        linger_ms: int = 10,
        acks: str = "all",
        retries: int = 5,
    ) -> None:
        # Topic and bootstrap configuration.
        self.topic = topic or settings.OUT_TOPIC
        self.bootstrap = brokers or settings.KAFKA_BROKERS  
        # Producer tuning parameters.
        self.linger_ms = linger_ms
        self.acks = acks
        self.retries = retries
        # Producer instance created on first use.
        self._producer: Optional[KafkaProducer] = None

    # Ensure a KafkaProducer exists; create it lazily with safe JSON serializer.
    def _ensure_producer(self) -> None:
        """Lazy-init KafkaProducer with JSON serializer and configured options."""
        if self._producer is None:
            print(f"[KafkaWriter] Creating KafkaProducer: brokers={self.bootstrap}, topic={self.topic}")
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=self.bootstrap,
                    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                    linger_ms=self.linger_ms,
                    acks=self.acks,
                    retries=self.retries,
                )
                print("[KafkaWriter] KafkaProducer created successfully.")
            except Exception as e:
                print(f"[KafkaWriter][ERROR] Failed to create KafkaProducer: {e!r}")
                raise

    # Serialize and send an Alert to Kafka; log errors to stdout.
    def write(self, alert: Alert) -> None:
        """Send an Alert to Kafka (non-blocking send)."""
        print(f"[KafkaWriter] write() called for alert: device={getattr(alert, 'device_id', None)}, issue={getattr(alert, 'issue_type', None)}")
        try:
            if getattr(alert, "issue_type", None) == "unknown_device":
                print(f"[KafkaWriter] Skipping unknown device alert for {alert.device_id}")
                return
            
            self._ensure_producer()
            payload = _alert_to_dict(alert)
            print(f"[KafkaWriter] Sending payload: {payload}")
            self._producer.send(self.topic, payload)

            print(
                f"[KafkaWriter] Alert sent → topic='{self.topic}', "
                f"device='{alert.device_id}', issue='{alert.issue_type}', "
                f"time={payload.get('start_ts')}"
            )
        except Exception as e:
            print(f"[KafkaWriter][ERROR] send failed: {e!r}")

    # Flush producer buffers if the producer exists.
    def flush(self) -> None:
        """Flush any buffered messages to Kafka."""
        try:
            if self._producer:
                self._producer.flush()
        except Exception as e:
            print(f"[KafkaWriter] flush failed: {e!r}")

    # Flush and close the underlying producer if present.
    def close(self) -> None:
        """Gracefully flush and close the Kafka producer."""
        try:
            if self._producer:
                self._producer.flush()
                self._producer.close()
        except Exception as e:
            print(f"[KafkaWriter] close failed: {e!r}")
