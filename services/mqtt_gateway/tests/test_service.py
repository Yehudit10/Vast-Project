# services/mqtt_gateway/tests/test_service.py
# Purpose: Unit tests for the orchestration service using mocks for IO.

from __future__ import annotations
from unittest.mock import Mock
import pytest

from services.mqtt_gateway.models import ImageInfo
from services.mqtt_gateway.service import (
    ServiceConfig, Deps, IngestService, DefaultClock, DefaultIds
)


def make_info():
    return ImageInfo(
        sensor_id="camera-01",
        captured_ts=1761548130123,
        filename="garage_cam_01_20251027_121530.jpg",
        content_type="image/jpeg",
    )


def test_process_image_happy_path():
    # Arrange
    cfg = ServiceConfig(bucket="rover-images", kafka_topic="rover.images.meta.v1")

    image_store = Mock()
    image_store.put_object.return_value = ("abc123", 531245)

    producer = Mock()

    clock = DefaultClock()
    ids = Mock()
    ids.new_event_id.return_value = "11111111-1111-1111-1111-111111111111"

    service = IngestService(cfg, Deps(image_store=image_store, producer=producer, clock=clock, ids=ids))
    info = make_info()
    payload = b"\xff\xd8\xff\xdb\x00..."  # fake jpeg bytes

    # Act
    mobj, kev = service.process_image(info, payload)

    # Assert: storage call
    image_store.put_object.assert_called_once()
    args, kwargs = image_store.put_object.call_args
    assert kwargs["bucket"] == "rover-images"
    assert kwargs["content_type"] == "image/jpeg"
    assert kwargs["data"] == payload
    assert kwargs["key"].endswith("camera-01_1761548130123.jpg")

    # Assert: event produced
    producer.send.assert_called_once()
    p_args, p_kwargs = producer.send.call_args
    assert p_kwargs["topic"] == "rover.images.meta.v1"
    assert p_kwargs["key"] == "camera-01:1761548130123"
    val = p_kwargs["value"]
    assert val["event_id"] == "11111111-1111-1111-1111-111111111111"
    assert val["image"]["bucket"] == "rover-images"
    assert val["image"]["key"].endswith("camera-01_1761548130123.jpg")
    assert val["image"]["sha256"] == "abc123"
    assert val["image"]["size_bytes"] == 531245


def test_process_image_store_failure():
    cfg = ServiceConfig(bucket="rover-images", kafka_topic="rover.images.meta.v1")

    image_store = Mock()
    image_store.put_object.side_effect = RuntimeError("store down")

    producer = Mock()
    clock = DefaultClock()
    ids = DefaultIds()

    service = IngestService(cfg, Deps(image_store=image_store, producer=producer, clock=clock, ids=ids))
    info = make_info()
    payload = b"data"

    with pytest.raises(RuntimeError):
        service.process_image(info, payload)

    # Ensure producer not called when store fails
    producer.send.assert_not_called()


def test_process_image_producer_failure():
    cfg = ServiceConfig(bucket="rover-images", kafka_topic="rover.images.meta.v1")

    image_store = Mock()
    image_store.put_object.return_value = ("sha-ok", 10)

    producer = Mock()
    producer.send.side_effect = RuntimeError("kafka down")

    clock = DefaultClock()
    ids = DefaultIds()

    service = IngestService(cfg, Deps(image_store=image_store, producer=producer, clock=clock, ids=ids))
    info = make_info()
    payload = b"data"

    with pytest.raises(RuntimeError):
        service.process_image(info, payload)

    # Ensure we DID upload but failed on publish
    image_store.put_object.assert_called_once()
