import csv
import json
import os
from datetime import datetime, timedelta, timezone
from collections import deque
from confluent_kafka import Consumer

# ---------- CONFIG ----------
TOPIC = 'summaries.5m'
BOOTSTRAP = 'kafka:9092'
GROUP = 'daily-aggregator'

CSV_5MIN = 'aggregated_5min.csv'
CSV_DAILY = 'aggregated_daily.csv'

# intervals
INTERVAL_5MIN = 5           # produce 5-min rows every 5 minutes
INTERVAL_DAILY = 15         # read last 15 minutes from 5-min CSV and write daily summary

# ---------- Kafka consumer ----------
conf = {
    'bootstrap.servers': BOOTSTRAP,
    'group.id': GROUP,
    'auto.offset.reset': 'earliest'
}
consumer = Consumer(conf)
consumer.subscribe([TOPIC])

# ---------- helpers ----------
def now_utc():
    return datetime.now(timezone.utc)

def iso_to_dt(s: str) -> datetime:
    """Parse ISO timestamp; accept trailing Z or offset."""
    if not s:
        return None
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    return datetime.fromisoformat(s)

def write_csv_row(path, row, fieldnames):
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            writer.writeheader()
        writer.writerow(row)

def read_5min_rows_between(cutoff_start_dt, cutoff_end_dt):
    """Read aggregated_5min.csv and return list of parsed rows whose window_end is within [cutoff_start_dt, cutoff_end_dt]."""
    rows = []
    if not os.path.exists(CSV_5MIN):
        return rows
    with open(CSV_5MIN, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            # try to parse window_start/window_end; tolerate JSON mic_ids
            try:
                we = iso_to_dt(r.get('window_end') or r.get('window_end_iso') or '')
            except Exception:
                we = None
            if we is None:
                continue
            # include row if window_end is inside window (alternatively could check overlap)
            if cutoff_start_dt <= we <= cutoff_end_dt:
                try:
                    avg_v = float(r.get('avg_volume_db') or 0.0)
                except Exception:
                    avg_v = 0.0
                try:
                    max_v = float(r.get('max_volume_db') or 0.0)
                except Exception:
                    max_v = 0.0
                try:
                    anom = int(r.get('anomaly_count') or r.get('total_anomaly_count') or 0)
                except Exception:
                    anom = 0
                mic_ids_raw = r.get('mic_id') or r.get('mic_ids') or ''
                # try parse JSON list, otherwise keep as string
                mic_ids = None
                try:
                    mic_ids = json.loads(mic_ids_raw)
                except Exception:
                    mic_ids = [x.strip() for x in mic_ids_raw.split(',') if x.strip()]
                rows.append({
                    "window_start": r.get('window_start'),
                    "window_end": r.get('window_end'),
                    "avg_volume_db": avg_v,
                    "max_volume_db": max_v,
                    "anomaly_count": anom,
                    "mic_ids": mic_ids,
                    "raw": r
                })
    return rows

# ---------- runtime accumulators for 5-min summary ----------
# we'll accumulate incoming messages and produce 5-min summary from these (not from file).
accum = {
    "count": 0,
    "sum_avg": 0.0,
    "max_v": None,
    "total_anom": 0,
    "mic_ids_seen": []
}
window_5min_start = now_utc()
next_5min_write = window_5min_start + timedelta(minutes=INTERVAL_5MIN)

# prepare daily schedule
window_daily_next = now_utc() + timedelta(minutes=INTERVAL_DAILY)

print("📥 Listening for messages... (CTRL+C to stop)")

try:
    while True:
        msg = consumer.poll(1.0)
        now = now_utc()

        # --- handle incoming kafka message ---
        if msg is not None:
            if msg.error():
                print("Kafka error:", msg.error())
            else:
                try:
                    payload = json.loads(msg.value().decode('utf-8'))
                except Exception as e:
                    print("JSON decode error, skipping:", e)
                    payload = None

                if payload:
                    metrics = payload.get('metrics', {})
                    try:
                        avg_v = float(metrics.get('avg_volume_db', 0.0))
                        max_v = float(metrics.get('max_volume_db', avg_v))
                        anom = int(metrics.get('anomaly_count', 0))
                    except Exception:
                        # skip malformed metric
                        continue

                    mic_id = payload.get('mic_id')

                    # update 5-min accumulators
                    accum["count"] += 1
                    accum["sum_avg"] += avg_v
                    accum["max_v"] = max_v if accum["max_v"] is None else max(accum["max_v"], max_v)
                    accum["total_anom"] += anom
                    if mic_id and mic_id not in accum["mic_ids_seen"]:
                        accum["mic_ids_seen"].append(mic_id)

        # --- produce 5-min CSV row when it's time ---
        if now >= next_5min_write:
            window_end = now
            window_start = window_5min_start

            if accum["count"] > 0:
                row_5 = {
                    "mic_id": json.dumps(accum["mic_ids_seen"], ensure_ascii=False),
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "avg_volume_db": round(accum["sum_avg"] / accum["count"], 2),
                    "max_volume_db": accum["max_v"],
                    "anomaly_count": accum["total_anom"]
                }
            else:
                # no samples in this 5-min window
                row_5 = {
                    "mic_id": json.dumps([]),
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "avg_volume_db": "",
                    "max_volume_db": "",
                    "anomaly_count": 0
                }

            write_csv_row(CSV_5MIN, row_5, fieldnames=list(row_5.keys()))
            print("Wrote 5-min row:", row_5)

            # reset accumulators for next 5-min block
            accum = {"count": 0, "sum_avg": 0.0, "max_v": None, "total_anom": 0, "mic_ids_seen": []}
            window_5min_start = now
            next_5min_write = now + timedelta(minutes=INTERVAL_5MIN)

        # --- every INTERVAL_DAILY minutes: read last INTERVAL_DAILY minutes from CSV_5MIN and write to CSV_DAILY ---
        if now >= window_daily_next:
            import time
            time.sleep(1)

            cutoff_start = now - timedelta(minutes=INTERVAL_DAILY)
            cutoff_end = now
            rows = read_5min_rows_between(cutoff_start, cutoff_end)

            if rows:
                samples = len(rows)
                avg_of_avgs = round(sum(r["avg_volume_db"] for r in rows) / samples, 2)
                max_of_max = max(r["max_volume_db"] for r in rows)
                total_anom = sum(r["anomaly_count"] for r in rows)
                # union mic ids preserving order
                seen = []
                for r in rows:
                    for m in (r["mic_ids"] or []):
                        if m not in seen:
                            seen.append(m)
                mic_ids_out = seen
            else:
                samples = 0
                avg_of_avgs = ""
                max_of_max = ""
                total_anom = 0
                mic_ids_out = []

            daily_row = {
                "window_start": cutoff_start.isoformat(),
                "window_end": cutoff_end.isoformat(),
                "mic_ids": json.dumps(mic_ids_out, ensure_ascii=False),
                "samples_5min_rows": samples,
                "avg_of_avg_volume_db": avg_of_avgs,
                "max_volume_db": max_of_max,
                "total_anomaly_count": total_anom
            }
            write_csv_row(CSV_DAILY, daily_row, fieldnames=list(daily_row.keys()))
            print("Wrote 15-min daily summary (from 5-min CSV):", daily_row)

            window_daily_next = now + timedelta(minutes=INTERVAL_DAILY)

except KeyboardInterrupt:
    print("Stopping consumer...")

finally:
    consumer.close()
    print("Consumer closed.")


# import csv
# import json
# from datetime import datetime, timedelta
# from confluent_kafka import Consumer

# # Kafka consumer configuration
# conf = {
#     'bootstrap.servers': 'kafka:9092',
#     'group.id': 'daily-aggregator',
#     'auto.offset.reset': 'earliest'
# }

# consumer = Consumer(conf)
# consumer.subscribe(['summaries.5m'])

# # CSV file paths
# csv_5min = 'aggregated_5min.csv'
# csv_daily = 'aggregated_daily.csv'

# # Window settings
# window_5min_start = datetime.utcnow()
# window_daily_start = datetime.utcnow()
# results_5min = []

# print("📥 Listening for messages... (CTRL+C to stop)")

# try:
#     while True:
#         msg = consumer.poll(5.0)
#         if msg is None:
#             continue
#         if msg.error():
#             print("Error:", msg.error())
#             continue

#         # Decode message
#         data = json.loads(msg.value().decode('utf-8'))

#         # Append raw metrics to results list
#         results_5min.append(data)

#         now = datetime.utcnow()

#         # Write to 5-min CSV if 5 minutes passed
#         if now - window_5min_start >= timedelta(minutes=5):
#             if results_5min:
#                 avg_volume = sum(r['metrics']['avg_volume_db'] for r in results_5min) / len(results_5min)
#                 max_volume = max(r['metrics']['max_volume_db'] for r in results_5min)
#                 total_anomalies = sum(r['metrics']['anomaly_count'] for r in results_5min)

#                 result = {
#                     "mic_id": ", ".join(set(r["mic_id"] for r in results_5min)),
#                     "window_start": window_5min_start.isoformat(),
#                     "window_end": now.isoformat(),
#                     "avg_volume_db": round(avg_volume, 2),
#                     "max_volume_db": max_volume,
#                     "anomaly_count": total_anomalies
#                 }

#                 # Write to CSV
#                 with open(csv_5min, mode='a', newline='') as f:
#                     writer = csv.DictWriter(f, fieldnames=result.keys())
#                     if f.tell() == 0:
#                         writer.writeheader()
#                     writer.writerow(result)

#                 print("5-min summary written:", result)

#             results_5min = []
#             window_5min_start = now

#         # Write daily summary every 15 minutes (testing)
#         if now - window_daily_start >= timedelta(minutes=15):
#             # פה אפשר להכניס חישוב יומי אמיתי, לדוגמה ממוצע כל מה שנאסף
#             daily_summary = result  # בדוגמה הזאת, פשוט חוזר על התוצאה האחרונה
#             with open(csv_daily, mode='a', newline='') as f:
#                 writer = csv.DictWriter(f, fieldnames=daily_summary.keys())
#                 if f.tell() == 0:
#                     writer.writeheader()
#                 writer.writerow(daily_summary)

#             print("Daily summary written:", daily_summary)
#             window_daily_start = now

# except KeyboardInterrupt:
#     print("Stopping consumer...")

# finally:
#     consumer.close()
#     print("Consumer closed.")
