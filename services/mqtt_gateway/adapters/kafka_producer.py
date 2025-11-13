# services/mqtt_gateway/adapters/kafka_producer.py
# Confluent Kafka producer adapter with lazy imports for unit-test friendliness.

from __future__ import annotations
import json, importlib
from typing import Optional

from services.mqtt_gateway.io import EventBusProducer


class ConfluentEventBusProducer(EventBusProducer):
    """
    Thin wrapper over confluent_kafka. Handles JSON serialization and delivery errors.
    Lazy-imports confluent_kafka to keep unit tests independent of that binary dep.
    """

    def __init__(self, bootstrap_servers: str, client_id: str = "mqtt-gateway") -> None:
        if not bootstrap_servers:
            raise ValueError("bootstrap_servers required")
        ck = importlib.import_module("confluent_kafka")
        self._Producer = ck.Producer
        self._p = self._Producer({"bootstrap.servers": bootstrap_servers, "client.id": client_id})

    def _delivery(self, err, msg) -> None:
        if err is not None:
            raise RuntimeError(f"kafka delivery failed: {err.str()}")

    def send(self, topic: str, key: str, value: dict) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self._p.produce(topic=topic, key=key, value=payload, callback=self._delivery)
        self._p.poll(0)
        self._p.flush(5)
