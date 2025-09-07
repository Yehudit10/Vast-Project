# import random
# import time
# from prometheus_client import Gauge, start_http_server

# # Demo metrics
# active_sensors = Gauge("active_sensors", "Number of active sensors")
# sensor_status = Gauge("sensor_status", "1=active, 0=inactive", ["sensor"])

# # Optional extras used by some panels (safe to expose even אם לא משתמשות)
# query_latency_ms = Gauge("query_latency_ms", "Gateway query latency (ms)")
# error_rate = Gauge("error_rate", "Gateway error rate (0..1)")

# def main():
#     # listen on 0.0.0.0:8001 so Docker can reach it via host.docker.internal
#     start_http_server(8001, addr="0.0.0.0")

#     sensors = [f"sensor_{i:02d}" for i in range(60)]

#     while True:
#         # set a random number of active sensors
#         k = random.randint(20, 60)
#         active_sensors.set(k)

#         # update each sensor's status
#         p = k / len(sensors)
#         for s in sensors:
#             sensor_status.labels(sensor=s).set(1 if random.random() < p else 0)

#         # optional demo signals
#         query_latency_ms.set(random.uniform(20, 120))
#         error_rate.set(random.uniform(0.0, 0.01))

#         time.sleep(5)

# if __name__ == "__main__":
#     main()


# services/demo_exporter.py
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

SENSORS = [f"sensor_{i:03d}" for i in range(1, 41)]

def _tick():
    while True:
        now = datetime.now(timezone.utc).timestamp()
        active = 0
        for s in SENSORS:
            val = 1 if random.random() < 0.8 else 0
            SENSOR_STATUS.labels(sensor=s).set(val)
            if val:
                active += 1
                SENSOR_LAST_SEEN.labels(sensor=s).set(now)
        SENSORS_ACTIVE_TOTAL.set(active)
        time.sleep(5)

@app.route("/metrics")
def metrics():
    return Response(generate_latest(REG), mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    threading.Thread(target=_tick, daemon=True).start()
    app.run(host="0.0.0.0", port=8001)
