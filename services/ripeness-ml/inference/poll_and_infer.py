#!/usr/bin/env python3
"""
Simple polling service:
- Polls rows from `inference_logs` (Postgres)
- Downloads image from MinIO URL (or HTTP URL)
- Calls existing `infer_local.predict(path, onnx_path)`
- Writes results into `inference_results` table

Environment variables / CLI args:
  DB_DSN (or --db-dsn) - e.g. postgresql://user:pass@host:5432/dbname
  ONNX_PATH (optional) - path to onnx model; defaults to 'ripeness_mobilenet_v3.onnx'
  POLL_INTERVAL (seconds) - default 5
  BATCH_SIZE - rows per loop (default 10)

Notes / assumptions:
- `inference_logs` table must contain at least: id (pk), minio_url (text), fruit_name (text)
- If `inference_logs` has no processed flags, the script will set `processed=true` after successful writing.
"""
import argparse
import os
import time
import json
import tempfile
import logging
from typing import Optional

import requests
import psycopg2
import psycopg2.extras
from minio import Minio

# reuse predict from infer_local
from infer_local import predict as infer_predict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def download_image(url: str, minio_client: Optional[Minio] = None) -> str:
    """Download the image to a temporary file and return the path.
    Try HTTP(S) first, fallback to MinIO object get if url indicates bucket/object.
    """
    # Simple HTTP(S) fetch
    try:
        resp = requests.get(url, stream=True, timeout=15)
        resp.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        with open(tmp.name, "wb") as f:
            for chunk in resp.iter_content(1024 * 16):
                if chunk:
                    f.write(chunk)
        return tmp.name
    except Exception as e:
        logger.debug(f"HTTP fetch failed for {url}: {e}")

    # If url looks like minio or s3 style, try Minio client (requires endpoint + creds)
    if minio_client is None:
        raise RuntimeError(f"Unable to fetch image by HTTP and no Minio client available for {url}")

    # Expect url like: http://minio:9000/bucket/object or /bucket/object or bucket/object
    # Try to parse bucket and object naively
    path = url
    if "//" in url:
        path = url.split("//", 1)[1]
        # drop host
        if "/" in path:
            path = path.split("/", 1)[1]
    if "/" not in path:
        raise RuntimeError(f"Cannot parse MinIO path from url: {url}")
    bucket, obj = path.split("/", 1)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(obj)[1] or ".jpg")
    minio_client.fget_object(bucket, obj, tmp.name)
    return tmp.name


def ensure_results_table(conn):
    sql = '''
    CREATE TABLE IF NOT EXISTS inference_results (
      id serial PRIMARY KEY,
      log_id bigint,
      ts timestamptz DEFAULT now(),
      minio_url text,
      fruit_name text,
      prediction text,
      confidence double precision,
      probs jsonb,
      raw_output jsonb
    );
    CREATE INDEX IF NOT EXISTS idx_inference_results_log_id ON inference_results(log_id);
    '''
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def mark_log_processed(conn, log_id, processed=True):
    with conn.cursor() as cur:
        # attempt to add processed columns if missing
        try:
            cur.execute("ALTER TABLE inference_logs ADD COLUMN IF NOT EXISTS processed boolean DEFAULT false;")
            cur.execute("ALTER TABLE inference_logs ADD COLUMN IF NOT EXISTS processed_at timestamptz;")
        except Exception:
            pass
        cur.execute("UPDATE inference_logs SET processed = %s, processed_at = now() WHERE id = %s", (processed, log_id))
    conn.commit()


def process_one_row(conn, row, onnx_path, minio_client=None):
    log_id = row['id']
    url = row['minio_url']
    fruit = row.get('fruit_name') or row.get('fruit') or ''
    logger.info(f"Processing log id={log_id} url={url} fruit={fruit}")

    try:
        img_path = download_image(url, minio_client=minio_client)
    except Exception as e:
        logger.exception(f"Failed to download image for id={log_id}: {e}")
        return False

    try:
        pred_label, probs = infer_predict(img_path, onnx_path=onnx_path)
        # probs is expected numpy-like iterable
        if hasattr(probs, 'tolist'):
            probs_json = list(map(float, probs.tolist()))
        else:
            probs_json = [float(p) for p in probs]

        # Insert to inference_results
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO inference_results (log_id, minio_url, fruit_name, prediction, confidence, probs, raw_output) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (log_id, url, fruit, pred_label, float(max(probs_json)), json.dumps(probs_json), json.dumps({'probs': probs_json}))
            )
            res_id = cur.fetchone()[0]
        conn.commit()
        mark_log_processed(conn, log_id, processed=True)
        logger.info(f"Inserted result id={res_id} for log id={log_id} -> {pred_label}")
        return True
    except Exception as e:
        logger.exception(f"Failed to infer/insert result for id={log_id}: {e}")
        # do not mark processed; optionally store error
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE inference_logs ADD COLUMN IF NOT EXISTS last_error text;")
            cur.execute("UPDATE inference_logs SET last_error = %s WHERE id = %s", (str(e), log_id))
        conn.commit()
        return False
    finally:
        try:
            os.unlink(img_path)
        except Exception:
            pass


def claim_rows(conn, batch_size=10):
    # Claim rows by selecting for update skip locked
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("ALTER TABLE inference_logs ADD COLUMN IF NOT EXISTS processed boolean DEFAULT false;")
        cur.execute("SELECT id, minio_url, fruit_name FROM inference_logs WHERE processed = false ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED", (batch_size,))
        rows = cur.fetchall()
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-dsn", default=os.environ.get("DB_DSN") or os.environ.get("DATABASE_URL"))
    parser.add_argument("--onnx", default=os.environ.get("ONNX_PATH", "ripeness_mobilenet_v3.onnx"))
    parser.add_argument("--poll-interval", type=int, default=int(os.environ.get("POLL_INTERVAL", 5)))
    parser.add_argument("--batch", type=int, default=int(os.environ.get("BATCH_SIZE", 10)))
    parser.add_argument("--minio-endpoint", default=os.environ.get("MINIO_ENDPOINT"))
    parser.add_argument("--minio-access-key", default=os.environ.get("MINIO_ACCESS_KEY"))
    parser.add_argument("--minio-secret-key", default=os.environ.get("MINIO_SECRET_KEY"))
    args = parser.parse_args()

    if not args.db_dsn:
        raise SystemExit("DB DSN must be provided via --db-dsn or DB_DSN env var")

    minio_client = None
    if args.minio_endpoint and args.minio_access_key and args.minio_secret_key:
        minio_client = Minio(args.minio_endpoint, access_key=args.minio_access_key, secret_key=args.minio_secret_key, secure=False)
        logger.info("Minio client initialized")

    conn = psycopg2.connect(args.db_dsn)
    ensure_results_table(conn)

    logger.info("Starting poll loop")
    try:
        while True:
            rows = claim_rows(conn, batch_size=args.batch)
            if not rows:
                time.sleep(args.poll_interval)
                continue
            for row in rows:
                try:
                    process_one_row(conn, row, onnx_path=args.onnx, minio_client=minio_client)
                except Exception:
                    logger.exception(f"Unexpected error processing row {row.get('id')}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        logger.info("Interrupted, exiting")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
