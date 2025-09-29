import os, glob, datetime
import cv2 as cv

from config import PG, SAMPLES_DIR, FRUIT_TYPE, THRESHOLDS
from segment import segment_fruit
from heuristics import compute_features, classify_ripeness
from quality import quality_flags
from db import dsn, apply_sql_autocommit, ensure_schema, insert_detection, run_weekly_upsert
from urllib.parse import urlparse
from minio import Minio
from minio.error import S3Error
import numpy as np, cv2 as cv, io
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


def process_all():

    DSN = dsn(PG)
    apply_sql_autocommit(DSN, SCHEMA_SQL)
    apply_sql_autocommit(DSN, VIEW_SQL)

    con = psycopg.connect(DSN)

    with con.cursor() as cur:
        for ext in ("*.jpg","*.jpeg","*.png","*.webp"):
            if MINIO_URL:
                for cli, key in list_minio_objects():
                    try:
                        resp = cli.get_object(MINIO_BUCKET, key)
                        data = resp.read(); resp.close(); resp.release_conn()
                    except S3Error:
                        continue
                    img_arr = np.frombuffer(data, dtype=np.uint8)
                    img = cv.imdecode(img_arr, cv.IMREAD_COLOR)
                    if img is None: 
                        continue

                    mask, leaf_ratio = segment_fruit(img, FRUIT_TYPE)  # ← שימי לב: ב־segment_fruit צריך fruit
                    feat = compute_features(img, mask)
                    ripeness = classify_ripeness(feat, THRESHOLDS)
                    flags = quality_flags(feat, THRESHOLDS, leaf_ratio, mark_outlier=False)

                    insert_detection(cur, FRUIT_TYPE, datetime.datetime.now(), f"s3://{MINIO_BUCKET}/{key}", feat, ripeness, flags)
            else:
                for path in glob.glob(os.path.join(SAMPLES_DIR, ext)):
                    img = cv.imread(path)
                    if img is None:
                        continue
                    mask, leaf_ratio = segment_fruit(img)

                    feat = compute_features(img, mask)
                    ripeness = classify_ripeness(feat, THRESHOLDS)

                    flags = quality_flags(feat, THRESHOLDS, leaf_ratio, mark_outlier=False)

                    insert_detection(cur, FRUIT_TYPE, datetime.datetime.now(), path, feat, ripeness, flags)

    con.commit()
    run_weekly_upsert(con, ROLLUP_SQL)
    con.commit()

    con.close()

if __name__ == "__main__":
    process_all()
    print("Done. Inserted detections and updated weekly_rollups.")
