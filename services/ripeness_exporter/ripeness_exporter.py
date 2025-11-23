#!/usr/bin/env python3
import time
import psycopg2
from prometheus_client import start_http_server, Gauge
import signal
import sys

# ====== CONFIG ======
DB_HOST = "postgres"
DB_PORT = 5432
DB_USER = "missions_user"
DB_PASS = "pg123"
DB_NAME = "missions_db"

SCRAPE_INTERVAL = 30  # seconds
THRESHOLD_TASK = "ripeness"
THRESHOLD_LABEL = ""  # empty label as defined
PROMETHEUS_PORT = 9128

# ====== METRICS ======

# Ripeness weekly rollups
g_pct = Gauge("fruit_ripeness_pct", "Weekly ripeness pct (0-1)", ["device"])
g_cnt_ripe = Gauge("fruit_ripeness_cnt_ripe", "Count ripe", ["device"])
g_cnt_unripe = Gauge("fruit_ripeness_cnt_unripe", "Count unripe", ["device"])
g_cnt_overripe = Gauge("fruit_ripeness_cnt_overripe", "Count overripe", ["device"])
g_cnt_total = Gauge("fruit_ripeness_cnt_total", "Total fruits counted", ["device"])

# Threshold + alert state (based on rollup)
g_alert_state = Gauge("fruit_ripeness_alert_state", "1 if below threshold", ["device"])
g_threshold = Gauge("fruit_ripeness_threshold", "Ripeness threshold global")

# ====== NEW ALERT METRICS (From alerts table) ======

g_alerts_total = Gauge(
    "fruit_ripeness_alerts_total",
    "Total number of ripeness alerts for a device",
    ["device"]
)

g_alert_last_pct = Gauge(
    "fruit_ripeness_alert_last_pct",
    "pct_ripe from the last ripeness alert",
    ["device"]
)

g_alert_active = Gauge(
    "fruit_ripeness_alert_active",
    "1 if device currently has a ripeness alert (based on alerts table)",
    ["device"]
)


# ====== DB CONNECT ======
def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        dbname=DB_NAME,
    )


# ====== MAIN LOOP ======
def run_loop():
    while True:
        try:
            conn = get_conn()
            cur = conn.cursor()

            # =======================
            # FETCH threshold
            # =======================
            cur.execute("""
                SELECT threshold
                FROM task_thresholds
                WHERE task = %s AND label = %s
                LIMIT 1;
            """, (THRESHOLD_TASK, THRESHOLD_LABEL))
            row = cur.fetchone()
            threshold = float(row[0]) if row else 0.75
            g_threshold.set(threshold)

            # =======================
            # FETCH latest weekly rollups
            # =======================
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

                # SET rollup metrics
                g_pct.labels(dev).set(pct)
                g_cnt_ripe.labels(dev).set(c_r)
                g_cnt_unripe.labels(dev).set(c_u)
                g_cnt_overripe.labels(dev).set(c_o)
                g_cnt_total.labels(dev).set(c_t)

                # SET alert state from rollup
                alert_state = 1 if pct < threshold else 0
                g_alert_state.labels(dev).set(alert_state)

                # =======================
                # ALERTS TABLE → Prometheus
                # =======================

                # 1) Count alerts
                cur.execute("""
                    SELECT COUNT(*)
                    FROM alerts
                    WHERE alert_type LIKE 'ripeness%%'
                      AND device_id = %s;
                """, (dev,))
                alert_count = cur.fetchone()[0]
                g_alerts_total.labels(dev).set(alert_count)

                # 2) Last alert pct_ripe
                cur.execute("""
                    SELECT meta->>'pct_ripe'
                    FROM alerts
                    WHERE alert_type LIKE 'ripeness%%'
                      AND device_id = %s
                    ORDER BY started_at DESC
                    LIMIT 1;
                """, (dev,))
                last_alert = cur.fetchone()

                if last_alert and last_alert[0] is not None:
                    g_alert_last_pct.labels(dev).set(float(last_alert[0]))
                    g_alert_active.labels(dev).set(1)
                else:
                    g_alert_last_pct.labels(dev).set(0)
                    g_alert_active.labels(dev).set(0)

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
