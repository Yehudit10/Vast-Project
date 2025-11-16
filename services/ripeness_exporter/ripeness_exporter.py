#!/usr/bin/env python3
import time
import psycopg2
from prometheus_client import start_http_server, Gauge
import signal
import sys

DB_HOST = "postgres"
DB_PORT = 5432
DB_USER = "missions_user"
DB_PASS = "pg123"
DB_NAME = "missions_db"

SCRAPE_INTERVAL = 30
THRESHOLD_TASK = "ripeness"
THRESHOLD_LABEL = ""
PROMETHEUS_PORT = 9128

g_pct = Gauge("fruit_ripeness_pct", "Weekly ripeness pct (0-1)", ["device"])
g_cnt_ripe = Gauge("fruit_ripeness_cnt_ripe", "Count ripe", ["device"])
g_cnt_unripe = Gauge("fruit_ripeness_cnt_unripe", "Count unripe", ["device"])
g_cnt_overripe = Gauge("fruit_ripeness_cnt_overripe", "Count overripe", ["device"])
g_cnt_total = Gauge("fruit_ripeness_cnt_total", "Total fruits counted", ["device"])
g_alert_state = Gauge("fruit_ripeness_alert_state", "1 if below threshold", ["device"])
g_threshold = Gauge("fruit_ripeness_threshold", "Ripeness threshold global")

def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        dbname=DB_NAME,
    )

def run_loop():
    while True:
        try:
            conn = get_conn()
            cur = conn.cursor()

            cur.execute("""
                SELECT threshold
                FROM task_thresholds
                WHERE task = %s AND label = %s
                LIMIT 1;
            """, (THRESHOLD_TASK, THRESHOLD_LABEL))
            row = cur.fetchone()
            threshold = float(row[0]) if row else 0.75
            g_threshold.set(threshold)

            cur.execute("""
                SELECT device_id, pct_ripe, cnt_ripe, cnt_unripe,
                       cnt_overripe, cnt_total
                FROM ripeness_weekly_rollups_ts
                WHERE window_end = (
                    SELECT MAX(window_end)
                    FROM ripeness_weekly_rollups_ts
                );
            """)
            rows = cur.fetchall()

            for device_id, pct, c_r, c_u, c_o, c_t in rows:
                dev = device_id or "unknown"

                g_pct.labels(dev).set(pct)
                g_cnt_ripe.labels(dev).set(c_r)
                g_cnt_unripe.labels(dev).set(c_u)
                g_cnt_overripe.labels(dev).set(c_o)
                g_cnt_total.labels(dev).set(c_t)

                alert_state = 1 if pct < threshold else 0
                g_alert_state.labels(dev).set(alert_state)

            cur.close()
            conn.close()

        except Exception as e:
            print("ERROR:", e)

        time.sleep(SCRAPE_INTERVAL)

def shutdown(sig, frame):
    print("Shutting down exporter...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"Starting Prometheus exporter on port {PROMETHEUS_PORT} ...")
    start_http_server(PROMETHEUS_PORT)
    run_loop()
