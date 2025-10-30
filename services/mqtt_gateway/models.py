# services/mqtt_gateway/models.py
# Purpose: Typed, validated data contracts for MQTT→MinIO/Kafka mapping.
# Clean, testable models used across the service.

from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional


class MinioObject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bucket: str = Field(min_length=1)
    key: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    size_bytes: Optional[int] = Field(default=None, ge=0)
    sha256: Optional[str] = None


class ImageInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sensor_id: str = Field(min_length=1)
    captured_ts: int = Field(ge=0, description="epoch milliseconds")
    filename: str = Field(min_length=1)
    content_type: str = Field(min_length=1)

    @field_validator("content_type")
    @classmethod
    def normalize_ctype(cls, v: str) -> str:
        return v.strip().lower()


class KafkaEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 1
    event_id: str
    sensor_id: str
    captured_ts: int
    image: MinioObject
    telemetry: Optional[dict] = None
    producer: str = "mqtt-gateway"

    @property
    def key(self) -> str:
        """Kafka message key (partitioning & idempotency hint)."""
        return f"{self.sensor_id}:{self.captured_ts}"

