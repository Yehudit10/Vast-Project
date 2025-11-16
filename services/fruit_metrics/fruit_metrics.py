from fastapi import FastAPI
from starlette.responses import Response
from prometheus_client import Gauge, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
import psycopg2
import psycopg2.extras
import threading
import time
import os

REFRESH_EVERY = 10  # seconds

# ─────────────────────────────────────────────
# Connect to PostgreSQL directly
# ─────────────────────────────────────────────
def get_db_connection():
    return psycopg2.connect(
        host="postgres",
        port=5432,
        user="missions_user",
        password="pg123",
        dbname="missions_db"
    )

# ─────────────────────────────────────────────
# Create Prometheus registry
# ─────────────────────────────────────────────
reg = CollectorRegistry()

g_total = Gauge("fruit_alerts_total", "Total fruit alerts", registry=reg)
g_active = Gauge("fruit_alerts_active", "Active fruit alerts", registry=reg)
g_by_type = Gauge("fruit_alerts_by_type", "Alerts by type", ["type"], registry=reg)
g_by_severity = Gauge("fruit_alerts_by_severity", "Alerts by severity", ["severity"], registry=reg)
g_by_device = Gauge("fruit_alerts_by_device", "Alerts by device", ["device"], registry=reg)

# ─────────────────────────────────────────────
# Query the database
# ─────────────────────────────────────────────
def fetch_alerts():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM alerts")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print("DB ERROR:", e)
        return []

# ─────────────────────────────────────────────
# Metrics refresher loop
# ─────────────────────────────────────────────
def refresh_loop():
    while True:
        alerts = fetch_alerts()

        types = {}
        severities = {}
        devices = {}

        total = len(alerts)
        active = 0

        for a in alerts:
            # count active alerts
            if a.get("ended_at") is None:
                active += 1

            # count by type
            t = a.get("alert_type") or "unknown"
            types[t] = types.get(t, 0) + 1

            # count by severity
            sev = str(a.get("severity") or 1)
            severities[sev] = severities.get(sev, 0) + 1

            # count by device
            dev = a.get("device_id") or "unknown"
            devices[dev] = devices.get(dev, 0) + 1

        # update gauges
        g_total.set(total)
        g_active.set(active)

        for t, count in types.items():
            g_by_type.labels(t).set(count)

        for sev, count in severities.items():
            g_by_severity.labels(sev).set(count)

        for dev, count in devices.items():
            g_by_device.labels(dev).set(count)

        time.sleep(REFRESH_EVERY)

threading.Thread(target=refresh_loop, daemon=True).start()

# ─────────────────────────────────────────────
# FastAPI endpoint for Prometheus
# ─────────────────────────────────────────────
app = FastAPI()

@app.get("/metrics")
def metrics():
    return Response(generate_latest(reg), media_type=CONTENT_TYPE_LATEST)
