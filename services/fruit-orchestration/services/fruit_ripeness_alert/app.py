#!/usr/bin/env python3
import os, json, uuid, requests
from datetime import datetime, timedelta, timezone
from kafka import KafkaProducer
from token_bootstrap import get_service_token

# === Environment ===
DB_API_BASE = os.getenv("DB_API_BASE", "http://db_api_service:8001")
DB_API_TOKEN_FILE = os.getenv("DB_API_TOKEN_FILE", "/app/secret/db_api_token")
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
ALERT_TOPIC = os.getenv("ALERT_TOPIC", "alerts")
WINDOW_HOURS = int(os.getenv("WINDOW_HOURS", "168"))  # default = 7 days


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso(ts: datetime) -> str:
    return ts.replace(tzinfo=timezone.utc).isoformat()

def get_threshold(task_name="ripeness", headers=None):
    url = f"{DB_API_BASE}/api/task_thresholds"
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code >= 500:
            print(f"[WARN] thresholds API {r.status_code}, using default 0.8")
            return 0.8
        r.raise_for_status()
        try:
            data = r.json()
        except ValueError as je:
            print(f"[WARN] thresholds response is not JSON: {je}; text={r.text[:200]!r}")
            return 0.8
    except Exception as e:
        print(f"[WARN] thresholds fetch failed: {e}; using default 0.8")
        return 0.8

    # Supports both list and dict responses (rows/items/data)
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("rows") or data.get("items") or data.get("data") or []
        if not isinstance(rows, list):
            rows = []
    else:
        rows = []

    if not rows:
        print(f"[WARN] No thresholds found at all, using default 0.8")
        return 0.8

    match = next((row for row in rows if row.get("task") == task_name), None)
    if not match:
        print(f"[WARN] No threshold for task={task_name}, using default 0.8")
        return 0.8

    try:
        return float(match.get("threshold", 0.8))
    except Exception:
        return 0.8


from datetime import datetime, timezone

def get_rollups(window_start, window_end, headers=None):
    """
    Fetch data from ripeness_weekly_rollups_ts table and filter by time window.
    Works with both list response and dict response containing {"rows": [...]}.
    """
    url = f"{DB_API_BASE}/api/ripeness_weekly_rollups_ts"
    print(f"[DEBUG] Fetching from {url}", flush=True)

    try:
        r = requests.get(url, headers=headers, timeout=60)
        r.raise_for_status()
        try:
            data = r.json()
        except ValueError as je:
            print(f"[ERROR] response is not JSON: {je}; text={r.text[:300]}", flush=True)
            return []
    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] HTTP {r.status_code}: {r.text}", flush=True)
        return []
    except Exception as e:
        print(f"[ERROR] failed to fetch rollups: {e}", flush=True)
        return []

    # --- Normalize response structure ---
    if isinstance(data, dict):
        rows = data.get("rows") or data.get("items") or data.get("data") or []
        if not isinstance(rows, list):
            print(f"[WARN] unexpected dict shape, using empty list; keys={list(data.keys())}", flush=True)
            rows = []
    elif isinstance(data, list):
        rows = data
    else:
        print(f"[WARN] unexpected JSON type: {type(data).__name__}", flush=True)
        rows = []

    # --- Parse timestamps and filter by time window ---
    def parse_ts(ts_str: str) -> datetime:
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    filtered = []
    for row in rows:
        ts = parse_ts(str(row.get("ts", "")))
        if window_start <= ts <= window_end:
            filtered.append(row)

    print(f"[INFO] Retrieved {len(filtered)} rollups after filtering (out of {len(rows)} total)")
    return filtered


def send_kafka_alert(producer, device_id, ratio, threshold, run_id, rollup_id):
    alert = {
        "alert_id": str(uuid.uuid4()),
        "alert_type": "fruit_ripeness_high",
        "device_id": "device_id",
        "started_at": iso(now_utc()),
        "confidence": float(ratio),
        "severity": 3,
        "meta": {                      # 👈 Additional metadata is included here
            "run_id": str(run_id),
            "threshold": threshold,    # Save the threshold value as well
            "rollup_id": str(rollup_id),
            "description": f"{ratio*100:.1f}% ripe/overripe fruits"
        }
    }

    producer.send(ALERT_TOPIC, json.dumps(alert).encode("utf-8"))
    producer.flush()
    print(f"[ALERT] sent for {device_id}: {ratio*100:.1f}%")


def main():
    print("ello!")
    token = get_service_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Service-Token"] = token
        
    window_end = now_utc()
    window_start = window_end - timedelta(hours=WINDOW_HOURS)
    print(f"[INFO] Checking rollups {window_start} → {window_end}")

    threshold = get_threshold("ripeness", headers)
    print(f"[INFO] Using ripeness threshold: {threshold:.2f}")
    rows = get_rollups(window_start, window_end, headers)
    print(f"[INFO] Fetched {rows} rollup records")
    if not rows:
        print("[INFO] No data found.")
        return

    producer = KafkaProducer(bootstrap_servers=[KAFKA_BROKER])

    # Iterate through each device
    for row in rows:
        rollup_id = row.get("id")
        device_id = row.get("device_id")
        run_id = row.get("run_id")
        pct = row.get("pct_ripe", 0.0)
        if pct >= threshold:
            send_kafka_alert(producer, device_id, pct, threshold, run_id, rollup_id)
        else:
            print(f"[INFO] {device_id}: below threshold {pct:.2f} < {threshold:.2f}")

    producer.close()
    print("[DONE] process complete.")


if __name__ == "__main__":
    main()
