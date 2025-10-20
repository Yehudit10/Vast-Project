import os, io, json, time, logging
from typing import Dict, Any
from kafka import KafkaConsumer, KafkaProducer
from minio import Minio
from minio.error import S3Error
from PIL import Image
# TODO: import torch / real model if available

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
TASKS_TOPIC     = os.getenv("TASKS_TOPIC", "fruit.infer.tasks")
RESULTS_TOPIC   = os.getenv("RESULTS_TOPIC", "fruit.infer.results")
GROUP_ID        = os.getenv("GROUP_ID", "fruit-infer-workers")

MINIO_ENDPOINT  = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY= os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY= os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_SECURE    = os.getenv("MINIO_SECURE", "false").lower() == "true"

WEIGHTS_TS = os.getenv("LOCAL_WEIGHTS_TS", "/weights/fruit_cls_best.ts")
WEIGHTS_PT = os.getenv("LOCAL_WEIGHTS_PT", "/weights/fruit_cls_best.pt")

def load_image_from_minio(client: Minio, bucket: str, key: str) -> Image.Image:
    """Download image bytes from MinIO and open with PIL."""
    resp = client.get_object(bucket, key)
    data = resp.read()
    resp.close(); resp.release_conn()
    return Image.open(io.BytesIO(data)).convert("RGB")

def run_inference(img: Image.Image) -> Dict[str, Any]:
    """Replace this stub with real preprocessing/model inference."""
    start = time.time()
    # TODO: real model.predict(img)
    time.sleep(0.01)  # simulate latency
    return {
        "status": "defect",           # or "ok"
        "defect_type": "mold",
        "severity": 0.82,
        "metrics": {"conf": 0.91},
        "latency_ms": (time.time() - start) * 1000
    }

def main():
    logging.info("Starting fruit_infer_worker…")
    minio = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY,
                  secret_key=MINIO_SECRET_KEY, secure=MINIO_SECURE)

    consumer = KafkaConsumer(
        TASKS_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=False,  # commit only after success
        auto_offset_reset="latest",
        max_poll_records=50,
    )
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        acks="all"
    )

    # TODO: load your model weights here (once)
    # model = load_model(WEIGHTS_TS or WEIGHTS_PT)

    try:
        for msg in consumer:
            task = msg.value       # {"bucket": "...", "key": "...", "ts": "..."}
            bkt, key = task["bucket"], task["key"]
            logging.info("Processing %s/%s", bkt, key)
            try:
                img   = load_image_from_minio(minio, bkt, key)
                infer = run_inference(img)
                out = {
                    "image_key": key,
                    "bucket": bkt,
                    "status": infer["status"],
                    "defect_type": infer.get("defect_type"),
                    "severity": infer.get("severity"),
                    "metrics": infer.get("metrics"),
                    "latency_ms": infer.get("latency_ms"),
                    "ts": task.get("ts"),
                }
                producer.send(RESULTS_TOPIC, out); producer.flush()
                consumer.commit()
            except Exception as e:
                logging.exception("Failed %s/%s: %s", bkt, key, e)
                time.sleep(0.3)  # small backoff
    finally:
        consumer.close(); producer.close()

if __name__ == "__main__":
    main()
