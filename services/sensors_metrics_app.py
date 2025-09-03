from __future__ import annotations
import random, time, threading
from datetime import datetime, timezone
from flask import Flask, Response
from prometheus_client import CollectorRegistry, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
REG = CollectorRegistry()

SENSOR_STATUS = Gauge("sensor_status", "1=active, 0=inactive", ["sensor"], registry=REG)
SENSORS_ACTIVE_TOTAL = Gauge("sensors_active_total", "Active sensors total", registry=REG)
SENSOR_LAST_SEEN = Gauge("sensor_last_seen_timestamp_seconds", "Last seen (unix ts)", ["sensor"], registry=REG)

SENSORS = [f"sensor_{i:03d}" for i in range(1, 41)]  # 40 sensors demo

def _tick():
    while True:
        active_count = 0
        now = datetime.now(timezone.utc).timestamp()
        for s in SENSORS:
            val = 1 if random.random() < 0.8 else 0  # ~80% active
            SENSOR_STATUS.labels(sensor=s).set(val)
            if val == 1:
                active_count += 1
                SENSOR_LAST_SEEN.labels(sensor=s).set(now)
        SENSORS_ACTIVE_TOTAL.set(active_count)
        time.sleep(5)

@app.route("/metrics")
def metrics():
    return Response(generate_latest(REG), mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    threading.Thread(target=_tick, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
