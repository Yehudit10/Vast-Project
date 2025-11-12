from unittest.mock import Mock
import pytest

from services.mqtt_gateway.models import ImageInfo
from services.mqtt_gateway.service import ServiceConfig, Deps, IngestService, DefaultClock, DefaultIds

def make_info():
    return ImageInfo(sensor_id="s1", captured_ts=1000, filename="a.jpg", content_type="image/jpeg")

def test_retry_on_store_once_then_success():
    cfg = ServiceConfig(bucket="b", kafka_topic="t")
    store = Mock()
    store.put_object.side_effect = [RuntimeError("flaky"), ("sha", 3)]
    prod = Mock()
    svc = IngestService(cfg, Deps(store, prod, DefaultClock(), DefaultIds()))
    m, e = svc.process_image(make_info(), b"xxx")
    assert prod.send.called

def test_retry_on_producer_once_then_success():
    cfg = ServiceConfig(bucket="b", kafka_topic="t")
    store = Mock()
    store.put_object.return_value = ("sha", 3)
    prod = Mock()
    prod.send.side_effect = [RuntimeError("flaky"), None]
    svc = IngestService(cfg, Deps(store, prod, DefaultClock(), DefaultIds()))
    m, e = svc.process_image(make_info(), b"xxx")
    assert prod.send.call_count == 2

def test_retry_exhaust_raises():
    cfg = ServiceConfig(bucket="b", kafka_topic="t")
    store = Mock()
    store.put_object.side_effect = RuntimeError("down")
    prod = Mock()
    svc = IngestService(cfg, Deps(store, prod, DefaultClock(), DefaultIds()))
    with pytest.raises(RuntimeError):
        svc.process_image(make_info(), b"xxx")
