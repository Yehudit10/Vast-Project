# services/mqtt_gateway/main.py
# MQTT consumer → build ImageInfo → process via IngestService.
# Designed for Docker. All configuration by env vars.
from __future__ import annotations

from prometheus_client import Counter, Histogram, start_http_server
import logging
from services.mqtt_gateway.config import load_config

import os, signal, sys, time, pathlib
from typing import Tuple
from paho.mqtt.client import Client, MQTTv5, CallbackAPIVersion
import paho.mqtt.client as mqtt
import json, threading
from typing import Optional, Dict, Tuple as _Tuple

from services.mqtt_gateway.models import ImageInfo
from services.mqtt_gateway.service import (
    ServiceConfig, Deps, IngestService, DefaultClock, DefaultIds
)
from services.mqtt_gateway.adapters.minio_store import Boto3ImageStore
from services.mqtt_gateway.adapters.kafka_producer import ConfluentEventBusProducer

TELEMETRY_TOPIC   = os.getenv("MQTT_TOPIC_TEL", "MQTT/telemetry/#")
TELEMETRY_TTL_SEC = int(os.getenv("TELEMETRY_TTL_SEC", "10"))  # seconds

# --------- Metrics & Logging ---------
INGEST_OK   = Counter("gateway_ingest_success_total", "successful publishes")
INGEST_FAIL = Counter("gateway_ingest_fail_total", "failed publishes")
INGEST_LAT  = Histogram("gateway_ingest_latency_ms", "ingest latency (ms)")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("mqtt-gateway")


# --------- Topic parser (mirrors your existing convention) ---------
def parse_topic(topic: str, filename_fallback: str = "image.jpg") -> Tuple[str, int, str, str]:
    """
    Returns (sensor_id, ts_ms, content_type, filename)
    Topic format: MQTT/imagery/{camera}/{ts_ms}/{ctype_safe}/{filename}
    """
    parts = [p for p in topic.split("/") if p]
    try:
        i = parts.index("imagery")
    except ValueError:
        return ("unknown", int(time.time() * 1000), "application/octet-stream", filename_fallback)

    sensor = parts[i + 1] if len(parts) > i + 1 else "unknown"
    ts_ms = int(parts[i + 2]) if len(parts) > i + 2 and parts[i + 2].isdigit() else int(time.time() * 1000)
    ctype = (parts[i + 3] if len(parts) > i + 3 else "application_octet-stream").replace("_", "/")
    fname = parts[i + 4] if len(parts) > i + 4 else filename_fallback
    return (sensor, ts_ms, ctype, fname)

# sensor_id -> (ts_ms, telemetry_dict)
_telemetry_cache: Dict[str, _Tuple[int, dict]] = {}
_telemetry_lock = threading.Lock()

def parse_tel_topic(topic: str) -> _Tuple[str, int]:
    """
    Parse telemetry topic: MQTT/telemetry/{sensor_id}/{ts_ms}
    Returns (sensor_id, ts_ms).
    """
    parts = [p for p in topic.split("/") if p]
    try:
        i = parts.index("telemetry")
    except ValueError:
        return ("unknown", int(time.time() * 1000))
    sensor = parts[i + 1] if len(parts) > i + 1 else "unknown"
    ts_ms  = int(parts[i + 2]) if len(parts) > i + 2 and parts[i + 2].isdigit() else int(time.time() * 1000)
    return (sensor, ts_ms)

def put_telemetry(sensor_id: str, ts_ms: int, tel: dict) -> None:
    """Store latest telemetry per sensor (monotonic by ts_ms)."""
    with _telemetry_lock:
        prev = _telemetry_cache.get(sensor_id)
        if (not prev) or ts_ms >= prev[0]:
            _telemetry_cache[sensor_id] = (ts_ms, tel)

def get_telemetry_for(sensor_id: str, captured_ts: int) -> Optional[dict]:
    """
    Return telemetry if within TTL window relative to captured_ts.
    """
    with _telemetry_lock:
        row = _telemetry_cache.get(sensor_id)
    if not row:
        return None
    ts_ms, tel = row
    if abs(captured_ts - ts_ms) <= TELEMETRY_TTL_SEC * 1000:
        return tel
    return None

def make_service_from_cfg(cfg) -> IngestService:
    store = Boto3ImageStore(
        endpoint_url=cfg.minio_endpoint,
        access_key=cfg.minio_access_key,
        secret_key=cfg.minio_secret_key,
    )
    producer = ConfluentEventBusProducer(bootstrap_servers=cfg.kafka_bootstrap)
    s_cfg = ServiceConfig(bucket=cfg.minio_bucket, kafka_topic=cfg.kafka_topic)
    deps = Deps(image_store=store, producer=producer, clock=DefaultClock(), ids=DefaultIds())
    return IngestService(s_cfg, deps)

def main() -> None:
    cfg = load_config()
    start_http_server(cfg.metrics_port, addr="0.0.0.0")
    log.info("metrics server started on :%d", cfg.metrics_port)
    service = make_service_from_cfg(cfg)

    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cfg.mqtt_client_id, protocol=MQTTv5)
    stop = False

    def on_connect(c, u, flags, rc, props):
        if rc == 0:
            log.info("mqtt connected, subscribing %s", cfg.mqtt_topic)
            c.subscribe(cfg.mqtt_topic, qos=1)
            c.subscribe(TELEMETRY_TOPIC, qos=0)
        else:
            print(f"[mqtt] connect failed rc={rc}")

    def on_message(c, u, msg):
        if "/telemetry/" in msg.topic:
            try:
                sensor, ts_ms, ctype, fname = parse_topic(msg.topic)
                tel = json.loads(msg.payload.decode("utf-8"))
                put_telemetry(sensor, ts_ms, tel)
                log.debug("telemetry cached sensor=%s ts=%d", sensor, ts_ms)
            except Exception as e:
                log.warning("bad telemetry message: %s", e, exc_info=False)
            return
        
        # ---- image branch ----
        with INGEST_LAT.time():
            try:
                # ✅ parse the image topic to get required fields
                sensor, ts_ms, ctype, fname = parse_topic(msg.topic)

                # build ImageInfo from topic + payload mime
                info = ImageInfo(
                    sensor_id=sensor,
                    captured_ts=ts_ms,
                    filename=fname,
                    content_type=ctype,
                )

                # match last telemetry (if within TTL)
                tel = get_telemetry_for(sensor, ts_ms)

                # pass telemetry down to the service
                _m, _e = service.process_image(info, msg.payload, telemetry=tel)

                INGEST_OK.inc()
                log.info(
                    "ingest ok sensor=%s ts=%s key=%s tel=%s",
                    sensor, ts_ms, _m.key, "yes" if tel else "no"
                )
            except Exception as e:
                INGEST_FAIL.inc()
                log.error("ingest error: %s", e, exc_info=False)

    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=8)
    client.connect(cfg.mqtt_host, cfg.mqtt_port, keepalive=60)
    client.loop_start()

    def _stop(*_):
        nonlocal stop
        stop = True
        client.loop_stop()
        client.disconnect()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    log.info("gateway running…")
    while not stop:
        time.sleep(0.5)
    log.info("gateway stopped.")

if __name__ == "__main__":
    main()
