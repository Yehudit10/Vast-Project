import os, datetime, numpy as np
import cv2 as cv
import requests
from urllib.parse import quote
from urllib.parse import urlparse, unquote
from minio import Minio
from quality import quality_flags

from segment import segment_fruit
from heuristics import compute_features, classify_ripeness
from config import PG, SAMPLES_DIR, FRUIT_TYPE, THRESHOLDS, LOOKBACK_DAYS, READ_FROM_LOGS
from db import dsn, apply_sql_autocommit, ensure_schema, insert_detection, run_weekly_upsert, fetch_inference_logs
from urllib.parse import urlparse, quote
import numpy as np, cv2 as cv
import psycopg
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT/"deploy/sql/01_schema.sql"
VIEW_SQL   = ROOT/"deploy/sql/02_rollup_view.sql"
ROLLUP_SQL = ROOT/"deploy/sql/03_weekly_upsert.sql"
MINIO_URL   = os.getenv("MINIO_URL")
MINIO_AK    = os.getenv("MINIO_ACCESS_KEY")
MINIO_SK    = os.getenv("MINIO_SECRET_KEY")
MINIO_BUCKET= os.getenv("MINIO_BUCKET", "imagery")
MINIO_PREFIX= os.getenv("MINIO_PREFIX", f"{FRUIT_TYPE}/test")

def list_minio_objects():
    u = urlparse(MINIO_URL); secure = (u.scheme == "https")
    cli = Minio(u.netloc, access_key=MINIO_AK, secret_key=MINIO_SK, secure=secure)
    for o in cli.list_objects(MINIO_BUCKET, prefix=MINIO_PREFIX, recursive=True):
        key = o.object_name
        if key.lower().endswith((".jpg",".jpeg",".png",".webp",".bmp")):
            yield cli, key

def imread_from_any(url: str):
    u = urlparse(url)
    minio_base = os.getenv("MINIO_URL", "http://minio-hot-1:9000")
    mu = urlparse(minio_base)

    is_minio = (u.hostname == mu.hostname and (u.port or 80) == (mu.port or 80)) or \
               (u.hostname == "minio-hot-1" and (u.port or 80) == 9000)

    if is_minio:
        cli = Minio(
            f"{mu.hostname}:{mu.port or (443 if mu.scheme=='https' else 80)}",
            access_key=os.getenv("MINIO_ACCESS_KEY"),
            secret_key=os.getenv("MINIO_SECRET_KEY"),
            secure=(mu.scheme == "https"),
        )
        # path-style: /<bucket>/<key...>
        parts = u.path.lstrip("/").split("/", 1)
        if len(parts) != 2:
            raise RuntimeError(f"Bad MinIO URL path: {u.path}")
        bucket, key = parts[0], unquote(parts[1])

        resp = cli.get_object(bucket, key)
        data = resp.read()
        resp.close(); resp.release_conn()

        arr = np.frombuffer(data, dtype=np.uint8)
        return cv.imdecode(arr, cv.IMREAD_COLOR)

    safe = quote(url, safe="/:?=&%()[]")
    r = requests.get(safe, timeout=30)
    r.raise_for_status()
    arr = np.frombuffer(r.content, dtype=np.uint8)
    return cv.imdecode(arr, cv.IMREAD_COLOR)


def process_all():

    DSN = dsn(PG)

    lookback_days = int(os.getenv("LOOKBACK_DAYS", "7"))
    rows = fetch_inference_logs(PG, lookback_days=lookback_days,
                                fruit_filter=None, limit=None)
    inserted = 0
    with psycopg.connect(DSN) as con:
        with con.cursor() as cur:
            for fruit_type_raw, image_url in rows:
                try:
                    
                    
                    fruit = fruit_type_raw
                    img = imread_from_any(image_url)
                    if img is None:
                        print(f"[skip] cannot read image: {image_url}")
                        continue

                    mask, leaf_ratio = segment_fruit(img, fruit)
                    feat = compute_features(img, mask)
                    ripeness = classify_ripeness(feat,THRESHOLDS)
                    flags = quality_flags(feat, THRESHOLDS, leaf_ratio, mark_outlier=False)  


                    insert_detection(cur, fruit, datetime.datetime.now(), image_url,
                                     feat, ripeness, flags)
                    inserted += 1

                except Exception as e:
                    print(f"[warn] {image_url} | {e}", flush=True)
                    con.rollback()
        con.commit()
        run_weekly_upsert(con, ROLLUP_SQL)
        con.commit()
    return inserted


if __name__ == "__main__":
    inserted = process_all()
    print(f"Done. Inserted detections {inserted} and updated weekly_rollups.")
