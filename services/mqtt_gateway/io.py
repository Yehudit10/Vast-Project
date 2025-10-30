# services/mqtt_gateway/io.py
# Purpose: IO interfaces (protocols) used by the service for testability.

from __future__ import annotations
from typing import Protocol, Optional, runtime_checkable


@runtime_checkable
class ImageStore(Protocol):
    def put_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str,
    ) -> tuple[str, int]:
        """
        Uploads bytes to object storage.
        Returns: (sha256_hex, size_bytes)
        Must raise an exception on failure.
        """


@runtime_checkable
class EventBusProducer(Protocol):
    def send(self, topic: str, key: str, value: dict) -> None:
        """
        Publishes a message to an event bus (e.g., Kafka).
        Must raise an exception on failure.
        """


class Clock(Protocol):
    def now_ms(self) -> int:
        """Epoch milliseconds (used mostly for timestamps in logs/metrics)."""


class IdGenerator(Protocol):
    def new_event_id(self) -> str:
        """Return a new UUID string for event_id."""
