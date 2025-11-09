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
WINDOW_HOURS = int(os.getenv("WINDOW_HOURS", "168")) 


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso(ts: datetime) -> str:
    return ts.replace(tzinfo=timezone.utc).isoformat()

def get_threshold(task_name="ripeness", headers=None):
    """שולף את אחוז הסף מהטבלה task_thresholds לפי שם המשימה."""
    url = f"{DB_API_BASE}/api/tables/task_thresholds"
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    rows = r.json().get("rows", [])
    if not rows:
        print(f"[WARN] No thresholds found at all, using default 0.8")
        return 0.8
        
    match = next((row for row in rows if row.get("task") == task_name), None)
    if not match:
        print(f"[WARN] No threshold found for task={task_name}, using default 0.8")
        return 0.8

    threshold = float(match.get("threshold", 0.8))
    print(f"[INFO] Task '{task_name}' threshold: {threshold*100:.1f}%")
    return threshold
from datetime import datetime, timezone

def get_rollups(window_start, window_end, headers=None):
    """
    שולפת את כל הרשומות מהטבלה ripeness_weekly_rollups_ts
    ואז מסננת לפי טווח התאריכים (window_start → window_end) בפייתון.
    """
    url = f"{DB_API_BASE}/api/tables/ripeness_weekly_rollups_ts"
    print(f"[DEBUG] Fetching full table from {url}", flush=True)

    try:
        # שולף את כל הנתונים (בלי פילטרים)
        r = requests.get(url, headers=headers, timeout=60)
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] HTTP {r.status_code}: {r.text}", flush=True)
        return []
    except Exception as e:
        print(f"[ERROR] failed to fetch rollups: {e}", flush=True)
        return []

    data = r.json()
    rows = data.get("rows", data)

   
    def parse_ts(ts_str: str) -> datetime:
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    filtered = []
    for row in rows:
        ts = parse_ts(row.get("ts", ""))
        if window_start <= ts <= window_end:
            filtered.append(row)

    print(f"[INFO] Retrieved {len(filtered)} rollups after filtering (out of {len(rows)} total)")
    return filtered

def send_kafka_alert(producer, device_id, ratio, threshold):
    alert = {
    "alert_id": str(uuid.uuid4()),
    "alert_type": "fruit_ripeness_high",
    "device_id": device_id,
    "started_at": iso(now_utc()),
    "confidence": float(ratio),
    "severity": 3,
    "threshold": threshold,               
    "description": f"{ratio*100:.1f}% ripe/overripe fruits",  # <── וגם את זה
    }

    producer.send(ALERT_TOPIC, json.dumps(alert).encode("utf-8"))
    producer.flush()
    print(f"[ALERT] sent for {device_id}: {ratio*100:.1f}%")

def main():
    token = get_service_token()   
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Service-Token"] = token
        
    window_end = now_utc()
    window_start = window_end - timedelta(hours=WINDOW_HOURS)
    print(f"[INFO] Checking rollups {window_start} → {window_end}")

    threshold = get_threshold("ripeness", headers)
    rows = get_rollups(window_start, window_end, headers)
    if not rows:
        print("[INFO] No data found.")
        return

    producer = KafkaProducer(bootstrap_servers=[KAFKA_BROKER])

    # iterate each device
    for row in rows:
        device_id = row.get("device_id")
        pct = row.get("pct_ripe", 0.0)
        if pct >= threshold:
            send_kafka_alert(producer, device_id, pct, threshold)
        else:
            print(f"[INFO] {device_id}: below threshold {pct:.2f} < {threshold:.2f}")

    producer.close()
    print("[DONE] process complete.")

if __name__ == "__main__":
    main()
