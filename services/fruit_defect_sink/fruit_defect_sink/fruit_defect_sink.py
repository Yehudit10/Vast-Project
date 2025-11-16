#!/usr/bin/env python3
import os
import sys
import json
import signal
import logging
from datetime import datetime, timezone
from uuid import uuid4

from confluent_kafka import Consumer, Producer
import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)

# ==========================
# Config from environment
# ==========================

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
CONSUME_TOPIC = os.getenv("FRUIT_DISPATCHED_TOPIC", "inference.dispatched.fruit")
ALERTS_TOPIC = os.getenv("ALERTS_TOPIC", "alerts")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "fruit-defect-sink")

PG_HOST = os.getenv("PGHOST", "postgres")
PG_PORT = int(os.getenv("PGPORT", "5432"))
PG_DB = os.getenv("PGDATABASE", "missions_db")
PG_USER = os.getenv("PGUSER", "missions_user")
PG_PASSWORD = os.getenv("PGPASSWORD", "pg123")


# ==========================
# Postgres helpers
# ==========================

def get_pg_conn():
    logging.info(
        "connecting to Postgres: host=%s db=%s user=%s",
        PG_HOST,
        PG_DB,
        PG_USER,
    )
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD,
    )
    conn.autocommit = True
    return conn


INSERT_SQL = """
INSERT INTO public.fruit_defect_predictions (
    ts,
    bucket,
    object_key,
    image_uri,
    label,
    score,
    confidence,
    latency_ms_http,
    latency_ms_model,
    device_id,
    idem_key,
    corr_id,
    extra
)
VALUES (
    %(ts)s,
    %(bucket)s,
    %(object_key)s,
    %(image_uri)s,
    %(label)s,
    %(score)s,
    %(confidence)s,
    %(latency_ms_http)s,
    %(latency_ms_model)s,
    %(device_id)s,
    %(idem_key)s,
    %(corr_id)s,
    %(extra)s
)
ON CONFLICT (idem_key) DO UPDATE
SET
    ts               = EXCLUDED.ts,
    bucket           = EXCLUDED.bucket,
    object_key       = EXCLUDED.object_key,
    image_uri        = EXCLUDED.image_uri,
    label            = EXCLUDED.label,
    score            = EXCLUDED.score,
    confidence       = EXCLUDED.confidence,
    latency_ms_http  = EXCLUDED.latency_ms_http,
    latency_ms_model = EXCLUDED.latency_ms_model,
    device_id        = EXCLUDED.device_id,
    corr_id          = EXCLUDED.corr_id,
    extra            = EXCLUDED.extra;
"""


# ==========================
# Kafka + processing
# ==========================

def parse_timestamp(ts_str: str | None) -> datetime:
    """
    Try to parse an ISO timestamp from the message.
    Falls back to 'now' in UTC if not provided / invalid.
    """
    if not ts_str:
        return datetime.now(timezone.utc)
    try:
        # handle "Z"
        if ts_str.endswith("Z"):
            ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except Exception:
        return datetime.now(timezone.utc)


def handle_message(envelope: dict, conn, producer: Producer):
    """
    Process a single message envelope: upsert to Postgres and maybe send alert.
    """
    # basic sanity
    if not envelope.get("ok", True):
        logging.warning("skipping message with ok=false: %s", envelope)
        return

    status = envelope.get("status")
    if status and status != 200:
        logging.warning("skipping message with non-200 status: %s", envelope)
        return

    body_raw = envelope.get("body")
    if not body_raw:
        logging.warning("no 'body' field in message, skipping")
        return
    
    # Support dict or string JSON
    if isinstance(body_raw, dict):
        body = body_raw
    else:
        try:
            body = json.loads(body_raw)
        except Exception as e:
            logging.error("failed to parse body JSON: %s; error=%s", body_raw, e)
            return
    # Parse result — can be missing (fruit-ok detection)
    result = body.get("result", {}) or {}

    event = envelope.get("event", {}) or {}
    
    # Extract bucket/key from body first
    bucket = body.get("bucket")
    object_key = body.get("key")
    
    # If missing — try event (legacy)
    if not bucket:
        bucket = event.get("bucket")
    if not object_key:
        object_key = event.get("key")
    
    # If still missing — try MinIO Key format: "imagery/fruit/tree/...jpg"
    minio_key = event.get("Key")
    if minio_key and (not bucket or not object_key):
        parts = minio_key.split("/", 1)
        if len(parts) == 2:
            bucket = bucket or parts[0]
            object_key = object_key or parts[1]

    image_uri = body.get("image_uri")
    if not image_uri and bucket and object_key:
        image_uri = f"s3://{bucket}/{object_key}"

    label = result.get("label") or body.get("label")
    score = result.get("score")
    confidence = result.get("confidence")

    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None

    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    latency_ms_model = result.get("latency_ms_model") or body.get("latency_ms_model")
    latency_ms_http = body.get("latency_ms")

    device_id = (
        event.get("device_id")
        or body.get("device_id")
        or envelope.get("device_id")
    )

    idem_key = body.get("idempotency_key") or envelope.get("event_id") or str(uuid4())
    corr_id = body.get("correlation_id") or envelope.get("event_id")

    ts_str = body.get("timestamp") or envelope.get("timestamp")
    ts = parse_timestamp(ts_str)

    extra = {
        "envelope": envelope,
        "body_parsed": body,
    }

    params = {
        "ts": ts,
        "bucket": bucket,
        "object_key": object_key,
        "image_uri": image_uri,
        "label": label,
        "score": score,
        "confidence": confidence,
        "latency_ms_http": latency_ms_http,
        "latency_ms_model": latency_ms_model,
        "device_id": device_id,
        "idem_key": idem_key,
        "corr_id": corr_id,
        "extra": json.dumps(extra),
    }

    # ==========================
    # Insert / upsert to Postgres
    # ==========================
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(INSERT_SQL, params)

    logging.info(
        "[sink] upserted fruit_defect_predictions idem_key=%s label=%s bucket=%s key=%s",
        idem_key,
        label,
        bucket,
        object_key,
    )

    # ==========================
    # Send alert if needed
    # ==========================
    maybe_send_alert(
        producer=producer,
        label=label,
        confidence=confidence,
        ts=ts,
        device_id=device_id,
        bucket=bucket,
        object_key=object_key,
        image_uri=image_uri,
        latency_ms_model=latency_ms_model,
        idem_key=idem_key,
    )


def maybe_send_alert(
    producer: Producer,
    label: str | None,
    confidence: float | None,
    ts: datetime,
    device_id: str | None,
    bucket: str | None,
    object_key: str | None,
    image_uri: str | None,
    latency_ms_model: float | None,
    idem_key: str,
):
    """ 
    Send an alert to the alerts topic if the label indicates a defect.
    """

    if label != "defect":
        return

    alert_id = idem_key or str(uuid4())

    alert = {
        # --- Required fields ---
        "alert_id": alert_id,
        "alert_type": "fruit_defect_detected",
        "device_id": device_id or "unknown-device",
        "started_at": ts.astimezone(timezone.utc).isoformat(),

        # --- Optional / dynamic fields ---
        "ended_at": None,
        "confidence": confidence,
        # "severity": 3,
        # "area": None,
        # "lat": None,
        # "lon": None,
        "image_url": image_uri,
        # "vod": None,
        # "hls": None,
        "meta": {
            "bucket": bucket,
            "object_key": object_key,
            "latency_ms_model": latency_ms_model,
            "alert_source": "fruit_defect_sink",
        },
    }

    payload = json.dumps(alert).encode("utf-8")
    producer.produce(ALERTS_TOPIC, payload)
    producer.flush()

    logging.info(
        "[sink] sent alert to topic '%s' alert_id=%s device_id=%s label=%s",
        ALERTS_TOPIC,
        alert_id,
        device_id,
        label,
    )


# ==========================
# Main
# ==========================

running = True


def _handle_sig(signum, frame):
    global running
    logging.info("received signal %s, shutting down...", signum)
    running = False


def main():
    global running

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    consumer_conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "group.id": KAFKA_GROUP_ID,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": True,
    }

    consumer = Consumer(consumer_conf)
    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})

    conn = get_pg_conn()

    logging.info(
        "[sink] listening on %s → Postgres.fruit_defect_predictions + alerts",
        CONSUME_TOPIC,
    )
    consumer.subscribe([CONSUME_TOPIC])

    try:
        while running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue

            if msg.error():
                logging.error("Kafka error: %s", msg.error())
                continue

            try:
                envelope = json.loads(msg.value().decode("utf-8"))
            except Exception as e:
                logging.error("failed to decode message value: %s", e)
                continue

            try:
                handle_message(envelope, conn, producer)
            except psycopg2.Error as e:
                logging.error("Postgres error: %s", e)
                try:
                    conn.close()
                except Exception:
                    pass
                conn = get_pg_conn()
            except Exception as e:
                logging.exception("processing error: %s", e)

    finally:
        logging.info("closing consumer and postgres connection...")
        try:
            consumer.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

