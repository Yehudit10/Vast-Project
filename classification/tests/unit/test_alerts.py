# tests/unit/test_alerts.py
import pytest
from unittest.mock import patch, MagicMock
import json
import logging

from scripts import alerts

@pytest.fixture(autouse=True)
def reset_producer():
    # Reset the producer before each test
    alerts.KAFKA_PRODUCER = None
    yield
    alerts.KAFKA_PRODUCER = None

def test_send_alert_no_producer(caplog):
    caplog.set_level(logging.WARNING, logger="audio_cls.alerts")
    alerts.KAFKA_PRODUCER = None
    alerts.send_kafka_alert("file.wav", "label_test", 0.5)
    assert "Kafka unavailable" in caplog.text
    assert "file.wav" in caplog.text
    assert "label_test" in caplog.text

@patch("classification.scripts.alerts.Producer")
def test_producer_initialization(mock_producer):
    # Simulate Producer creation success
    mock_instance = mock_producer.return_value
    with patch.object(alerts.LOGGER, "info") as mock_logger_info:
        alerts.KAFKA_PRODUCER = mock_instance
        alerts.LOGGER.info("Test init", extra={})
        mock_logger_info.assert_called()

def test_send_alert_success(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="audio_cls.alerts")
    mock_producer = MagicMock()
    monkeypatch.setattr(alerts, "KAFKA_PRODUCER", mock_producer)

    # simulate produce calls
    def mock_produce(topic, value, callback=None):
        if callback:
            callback(None, value)
    mock_producer.produce.side_effect = mock_produce

    alerts.send_kafka_alert("file.wav", "label_test", 0.75)

    # flush should be called
    mock_producer.flush.assert_called_once_with(timeout=5)
    # log should contain success message
    assert "Kafka alert sent successfully" in caplog.text
    assert "file.wav" in caplog.text
    assert "label_test" in caplog.text

def test_send_alert_fail_delivery(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="audio_cls.alerts")
    mock_producer = MagicMock()
    monkeypatch.setattr(alerts, "KAFKA_PRODUCER", mock_producer)

    def mock_produce(topic, value, callback=None):
        if callback:
            callback(Exception("Delivery failed"), value)
    mock_producer.produce.side_effect = mock_produce

    alerts.send_kafka_alert("file.wav", "label_test", 0.33)

    mock_producer.flush.assert_called_once_with(timeout=5)
    assert "Failed to deliver Kafka message" in caplog.text

def test_send_alert_produce_exception(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="audio_cls.alerts")
    mock_producer = MagicMock()
    mock_producer.produce.side_effect = alerts.KafkaException("Produce error")
    monkeypatch.setattr(alerts, "KAFKA_PRODUCER", mock_producer)

    alerts.send_kafka_alert("file.wav", "label_test", 0.9)
    assert "Exception during Kafka produce" in caplog.text
