import os, glob, datetime
import cv2 as cv

from config import PG, SAMPLES_DIR, FRUIT_TYPE, THRESHOLDS
from segment import segment_fruit
from heuristics import compute_features, classify_ripeness
from quality import quality_flags
from db import dsn, apply_sql_autocommit, ensure_schema, insert_detection, run_weekly_upsert

import psycopg
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT/"deploy/sql/01_schema.sql"
VIEW_SQL   = ROOT/"deploy/sql/02_rollup_view.sql"
ROLLUP_SQL = ROOT/"deploy/sql/03_weekly_upsert.sql"

def process_all():
    # con = psycopg.connect(dsn(PG))
    # ensure_schema(con, SCHEMA_SQL)
    # ensure_schema(con, VIEW_SQL)

    DSN = dsn(PG)
    # DDL בחיבור קצר עם autocommit
    apply_sql_autocommit(DSN, SCHEMA_SQL)
    apply_sql_autocommit(DSN, VIEW_SQL)

    con = psycopg.connect(DSN)

    with con.cursor() as cur:
        for ext in ("*.jpg","*.jpeg","*.png","*.webp"):
            for path in glob.glob(os.path.join(SAMPLES_DIR, ext)):
                img = cv.imread(path)
                if img is None:
                    continue
                # קיבלנו גם leaf_ratio
                mask, leaf_ratio = segment_fruit(img)

                feat = compute_features(img, mask)
                ripeness = classify_ripeness(feat, THRESHOLDS)

                # כאן מעבירים את leaf_ratio
                flags = quality_flags(feat, THRESHOLDS, leaf_ratio, mark_outlier=False)

                insert_detection(cur, FRUIT_TYPE, datetime.datetime.now(), path, feat, ripeness, flags)

    con.commit()
    # לאחר הכנסת נתונים – הפקת Rollup שבועי
    run_weekly_upsert(con, ROLLUP_SQL)
    con.commit()

    con.close()

if __name__ == "__main__":
    process_all()
    print("Done. Inserted detections and updated weekly_rollups.")
