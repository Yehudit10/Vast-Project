# services/mqtt_gateway/service.py
# Purpose: Orchestrates the ingestion of an image payload:
# parse → store in MinIO (via ImageStore) → build Kafka event → publish (EventBusProducer).
# Pure business logic, with IO abstracted behind interfaces for unit testing.

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
from uuid import uuid4
import hashlib

from .models import ImageInfo, MinioObject, KafkaEvent
from .mapper import build_minio_key, map_to_objects
from .io import ImageStore, EventBusProducer, Clock, IdGenerator
import logging
log = logging.getLogger("ingest-service") 

def _sha256_hex(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


@dataclass(frozen=True)
class ServiceConfig:
    bucket: str
    kafka_topic: str


@dataclass
class Deps:
    image_store: ImageStore
    producer: EventBusProducer
    clock: Clock
    ids: IdGenerator


class DefaultClock(Clock):
    def now_ms(self) -> int:
        import time
        return int(time.time() * 1000)


class DefaultIds(IdGenerator):
    def new_event_id(self) -> str:
        return str(uuid4())


class IngestService:
    """
    Public API:
    - process_image(info, payload) -> (MinioObject, KafkaEvent)

    Notes:
    - No direct imports of storage/kafka SDKs here. Only interfaces.
    - Idempotency is enforced downstream by keying on (sensor_id, captured_ts).
    """

    def __init__(self, cfg: ServiceConfig, deps: Deps) -> None:
        self.cfg = cfg
        self.deps = deps

    def _retry(self, fn, attempts=3):
        last = None
        for i in range(1, attempts + 1):
            try:
                return fn()
            except Exception as e:
                last = e
                if i == attempts:
                    raise
        raise last

    def process_image(self, info: ImageInfo, payload: bytes, telemetry: Optional[dict] = None) -> Tuple[MinioObject, KafkaEvent]:

        # 1) Compute MinIO object key (stable contract)
        key = build_minio_key(info.sensor_id, info.captured_ts, info.filename)

        # 2) Upload to object storage
        sha, size = self._retry(lambda: self.deps.image_store.put_object(
        bucket=self.cfg.bucket, key=key, data=payload, content_type=info.content_type
    ))

        # 3) Build event (add sha/size and deterministic IDs)
        mobj, kev = map_to_objects(
            bucket=self.cfg.bucket,
            info=info,
            sha256=sha,
            size_bytes=size,
            event_id=self.deps.ids.new_event_id(),
            telemetry=telemetry,
        )

        if telemetry is not None:
            kev.telemetry = telemetry

        # 4) Publish to event bus

        try:
            self._retry(lambda: self.deps.producer.send(
                topic=self.cfg.kafka_topic, key=kev.key, value=kev.model_dump()
            ))
        except Exception as e:
            # Do not raise — MinIO write already succeeded. Log and continue.
            log.warning(
                "kafka publish failed (topic=%s, key=%s): %s",
                self.cfg.kafka_topic, kev.key, e
            )

        return mobj, kev
