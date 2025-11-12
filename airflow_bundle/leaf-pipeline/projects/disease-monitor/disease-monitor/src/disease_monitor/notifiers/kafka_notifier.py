from __future__ import annotations
import json, uuid, datetime, logging
from kafka import KafkaProducer
from typing import Dict, Any
from .base import Notifier

LOGGER = logging.getLogger(__name__)

def _json_default(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


class KafkaNotifier(Notifier):
    def __init__(self, brokers: str, topic: str):
        self.producer = KafkaProducer(
            bootstrap_servers=brokers.split(","),
            value_serializer=lambda v: json.dumps(v, default=_json_default).encode("utf-8"),
        )
        self.topic = topic

    def send(self, alert: Dict[str, Any]) -> None:
        msg = {
            "alert_id": alert.get("alert_id") or str(uuid.uuid4()),
            "alert_type": alert.get("rule", "disease_detected"),
            "device_id": alert.get("entity_id"),
            "started_at": alert.get("window_start"),
            "ended_at": alert.get("window_end"),
            "confidence": alert.get("score"),
            "severity": int(alert.get("meta", {}).get("severity", 1)),
            "area": alert.get("meta", {}).get("area"),
            "lat": alert.get("meta", {}).get("lat"),
            "lon": alert.get("meta", {}).get("lon"),
            "image_url": alert.get("meta", {}).get("image_url"),
            "vod": alert.get("meta", {}).get("vod"),
            "hls": alert.get("meta", {}).get("hls"),
            "meta": alert.get("meta", {}),
        }

        try:
            self.producer.send(self.topic, msg)
            self.producer.flush()
            LOGGER.info(
                "KafkaNotifier: sent alert %s to topic '%s' with rule '%s' (confidence=%.2f)",
                msg["alert_id"], self.topic, msg["alert_type"], msg["confidence"] or 0,
            )
        except Exception as e:
            LOGGER.error("KafkaNotifier failed to send alert: %s", e)
