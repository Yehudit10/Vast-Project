import pathlib, sys
import pytest

# Ensure project root on path
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from mqtt_ingest.app import parse_topic, DEFAULT_PREFIX

def test_parse_topic_valid():
    topic = "MQTT/imagery/camera-01/1730000000000/image_jpeg/img001.jpg"
    info = parse_topic(topic)
    assert info["camera"] == "camera-01"
    assert info["publish_ts_ms"] == 1730000000000
    assert info["content_type"] == "image/jpeg"
    assert info["filename"] == "img001.jpg"
    assert info["key"].startswith("camera-01/")
    assert info["key"].endswith("/img001.jpg")

def test_parse_topic_fallback():
    info = parse_topic("MQTT/weird/topic")
    assert info["camera"] == DEFAULT_PREFIX
    assert isinstance(info["publish_ts_ms"], int)
    assert info["content_type"] == "application/octet-stream"
    assert info["filename"].endswith(".bin")
    assert info["key"].startswith(f"{DEFAULT_PREFIX}/")
