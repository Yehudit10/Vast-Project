import json
import types
import os
import pytest

import classification.scripts.alerts as alerts


# ---------- test helpers ----------
class DummyMsg:
    def __init__(self, topic, partition, offset):
        self._t = topic
        self._p = partition
        self._o = offset
    def topic(self): return self._t
    def partition(self): return self._p
    def offset(self): return self._o


class DummyProducer:
    def __init__(self, *a, **kw):
        self._queue = []
        self._flushed = 0
    def produce(self, *, topic, value, callback=None):
        self._queue.append((topic, value))
        if callback:
            callback(None, DummyMsg(topic, 0, len(self._queue) - 1))
    def poll(self, _):  # api compatibility
        pass
    def flush(self, timeout):
        self._flushed += 1
        return 0  # 0 undelivered → success


@pytest.fixture(autouse=True)
def _clear_cache():
    alerts._producer_cache.clear()
    yield
    alerts._producer_cache.clear()


# ---------- tests ----------
def test_send_alert_success_and_payload(monkeypatch):
    dp = DummyProducer()
    monkeypatch.setattr(alerts, "Producer", lambda *_a, **_k: dp, raising=True)

    ok = alerts.send_alert(
        brokers="kafka:9092",
        topic="dev-robot-alerts",
        label="car",
        probs={"car": 0.9, "dog": 0.1},
        meta={"bucket": "b", "key": "k.wav"},
    )
    assert ok is True
    # Verify one message with proper JSON payload
    assert len(dp._queue) == 1
    topic, raw = dp._queue[0]
    assert topic == "dev-robot-alerts"
    payload = json.loads(raw.decode("utf-8"))
    assert payload["label"] == "car"
    assert payload["probs"]["car"] == pytest.approx(0.9)
    assert isinstance(payload["ts"], int)


def test_producer_cache_reuse(monkeypatch):
    calls = {"made": 0}
    def mk(*_a, **_k):
        calls["made"] += 1
        return DummyProducer()
    monkeypatch.setattr(alerts, "Producer", mk, raising=True)

    # First call creates a producer
    assert alerts.send_alert(brokers="kafka:9092", topic="t", label="x", probs={"x": 1.0})
    # Second call should reuse cache → no extra Producer()
    assert alerts.send_alert(brokers="kafka:9092", topic="t", label="y", probs={"y": 1.0})
    assert calls["made"] == 1
    assert len(alerts._producer_cache) == 1


def test_send_alert_flush_nonzero_returns_false(monkeypatch, caplog):
    class BadFlushProducer(DummyProducer):
        def flush(self, timeout):
            return 1  # 1 undelivered
    monkeypatch.setattr(alerts, "Producer", lambda *_a, **_k: BadFlushProducer(), raising=True)

    ok = alerts.send_alert(brokers="b:9092", topic="t", label="x", probs={"x": 1.0})
    assert ok is False
    assert any("undelivered" in rec.message for rec in caplog.records)


def test_send_alert_kafka_exception_on_init(monkeypatch, caplog):
    class DummyKafkaEx(alerts.KafkaException):  # use the module's class
        pass
    def boom(*_a, **_k):
        raise DummyKafkaEx("init failed")
    monkeypatch.setattr(alerts, "Producer", boom, raising=True)

    ok = alerts.send_alert(brokers="bad:9092", topic="t", label="x", probs={"x": 1.0})
    assert ok is False
    assert any("exception while producing" in rec.message or "Failed to initialize Kafka" in rec.message
               for rec in caplog.records)


def test_send_alert_buffer_error(monkeypatch, caplog):
    class BufErrProducer(DummyProducer):
        def produce(self, *a, **k):
            raise BufferError("local queue full")
    monkeypatch.setattr(alerts, "Producer", lambda *_a, **_k: BufErrProducer(), raising=True)

    ok = alerts.send_alert(brokers="b:9092", topic="t", label="x", probs={"x": 1.0})
    assert ok is False
    assert any("local queue full" in rec.message for rec in caplog.records)


def test_send_alert_runtime_error(monkeypatch, caplog):
    class BoomProducer(DummyProducer):
        def produce(self, *a, **k):
            raise RuntimeError("produce exploded")
    monkeypatch.setattr(alerts, "Producer", lambda *_a, **_k: BoomProducer(), raising=True)

    ok = alerts.send_alert(brokers="b:9092", topic="t", label="x", probs={"x": 1.0})
    assert ok is False
    assert any("produce error" in rec.message for rec in caplog.records)


def test_legacy_send_kafka_alert_reads_env(monkeypatch):
    # Check that env is read and forwarded into send_alert
    captured = {}
    def fake_send_alert(*, brokers, topic, label, probs, meta):
        captured["brokers"] = brokers
        captured["topic"] = topic
        captured["label"] = label
        captured["probs"] = probs
        captured["meta"] = meta
        return True

    monkeypatch.setenv("KAFKA_BROKERS", "env-b:9092")
    monkeypatch.setenv("ALERTS_TOPIC", "env-topic")
    monkeypatch.setattr(alerts, "send_alert", fake_send_alert, raising=True)

    ok = alerts.send_kafka_alert(file_path="/tmp/a.wav", label="car", prob=0.7)
    assert ok is True
    assert captured["brokers"] == "env-b:9092"
    assert captured["topic"] == "env-topic"
    assert captured["label"] == "car"
    assert captured["probs"] == {"car": 0.7}
    assert captured["meta"]["file_path"] == "/tmp/a.wav"


def test__delivery_report_logs_ok_and_err(caplog):
    # OK case
    alerts._delivery_report(None, DummyMsg("t", 0, 1))
    # Error case
    class Err: 
        def __str__(self): return "boom"
    alerts._delivery_report(Err(), DummyMsg("t", 0, 2))

    # We don't assert exact wording, just that both paths logged
    assert any("Kafka delivered" in r.message for r in caplog.records)
    assert any("Kafka delivery failed" in r.message for r in caplog.records)
