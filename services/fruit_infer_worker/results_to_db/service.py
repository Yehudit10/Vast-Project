import os, json, time, logging
from typing import List, Dict, Any
import requests
from kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
RESULTS_TOPIC   = os.getenv("RESULTS_TOPIC", "fruit.infer.results")
GROUP_ID        = os.getenv("GROUP_ID", "results-to-db")

API_URL       = os.getenv("API_URL", "http://db-api-service:8080/api/fruit_defect_results/")
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "super-secret-efrat")

BATCH_MAX = int(os.getenv("BATCH_MAX", "200"))
BATCH_MS  = int(os.getenv("BATCH_MS", "3000"))

def to_db_format(item: Dict[str, Any]) -> Dict[str, Any]:
    # Map streaming result → API schema; adjust if your schema differs.
    return {
        "fruit_id": item["image_key"],       # using image_key as fruit_id
        "status": item["status"],
        "defect_type": item.get("defect_type"),
        "severity": item.get("severity"),
        "metrics": item.get("metrics"),
        "latency_ms": item.get("latency_ms"),
    }

def send_batch(batch: List[Dict[str, Any]]):
    if not batch:
        return
    payload = {"results": batch}
    headers = {"X-Service-Token": SERVICE_TOKEN}
    for attempt in range(1, 6):
        try:
            r = requests.post(API_URL, json=payload, headers=headers, timeout=10)
            r.raise_for_status()
            logging.info("Inserted %d results to DB", len(batch))
            return
        except Exception as e:
            logging.warning("DB post failed (attempt %d): %s", attempt, e)
            time.sleep(min(2**attempt, 10))
    logging.error("Giving up on a batch of %d after retries", len(batch))

def main():
    consumer = KafkaConsumer(
        RESULTS_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=False,
        auto_offset_reset="latest",
        max_poll_records=500,
    )
    buf: List[Dict[str, Any]] = []
    last = time.time()
    try:
        for msg in consumer:
            buf.append(to_db_format(msg.value))
            now = time.time()
            if len(buf) >= BATCH_MAX or (now - last) * 1000 >= BATCH_MS:
                send_batch(buf); consumer.commit(); buf.clear(); last = now
    finally:
        if buf: send_batch(buf)
        consumer.close()

if __name__ == "__main__":
    main()
