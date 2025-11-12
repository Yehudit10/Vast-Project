# /src/pipeline/db.py
from __future__ import annotations
import os
from sqlalchemy import create_engine, text

def get_engine():
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise RuntimeError("DB_URL is not set in environment")
    # echo=False לשקט; אפשר True לדיבוג
    return create_engine(db_url, future=True)

# משפטי INSERT בהתאם לשדות שה-Runner מזין
# הערה: מיועד ל-PostgreSQL + PostGIS. אם SQLite – צריך להתאים (לשמור WKT כ-TEXT).
INSERT_DET = text("""
INSERT INTO anomalies (mission_id, device_id, ts, anomaly_type_id, severity, details, geom)
VALUES (:mission_id, :device_id, :ts, :anomaly_type_id, :severity, CAST(:details AS JSONB),
        ST_GeomFromText(:wkt_geom, 4326))
""")

INSERT_COUNT = text("""
INSERT INTO tile_stats (mission_id, tile_id, anomaly_score, geom)
VALUES (:mission_id, :tile_id, :anomaly_score, ST_GeomFromText(:wkt_geom, 4326))
""")

INSERT_QA = text("""
INSERT INTO qa_runs (details) VALUES (CAST(:details AS JSONB))
""")
