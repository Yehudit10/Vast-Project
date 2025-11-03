# scripts/ripeness_api.py
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime, timedelta
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "")) 

from weekly_ripeness_job import (
    get_conn,
    fetch_from_minio,
    load_image_for_model,
    predict_ripeness,
)

app = FastAPI(title="Ripeness Service")

class BatchRequest(BaseModel):
    since_ts: datetime | None = None   
    limit: int = 500

def run_batch(since_ts: datetime | None, limit: int) -> int:
    if since_ts is None:
        since_ts = datetime.utcnow() - timedelta(days=7)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
        SELECT il.id, il.ts, il.fruit_type, il.image_url
        FROM inference_logs il
        LEFT JOIN ripeness_predictions rp ON rp.inference_log_id = il.id
        WHERE il.ts >= %s
          AND rp.id IS NULL
        ORDER BY il.id ASC
        LIMIT %s;
        """, (since_ts, limit))
        rows = cur.fetchall()

    processed = 0
    for inflog_id, ts, fruit_type, image_url in rows:
        try:
            img_bytes = fetch_from_minio(image_url)
            tensor = load_image_for_model(img_bytes)
            label, score = predict_ripeness(tensor, fruit_type)
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute("""
                  INSERT INTO ripeness_predictions
                    (inference_log_id, ts, ripeness_label, ripeness_score, model_name)
                  VALUES (%s, now(), %s, %s, %s)
                  ON CONFLICT (inference_log_id) DO NOTHING;
                """, (inflog_id, label, score, os.getenv("MODEL_NAME","best_conditional")))
            processed += 1
        except Exception as e:
            print(f"[ERR] inflog_id={inflog_id} :: {e}")
    return processed

@app.get("/healthz")
def healthz(): return {"ok": True}

@app.post("/predict-batch")
def predict_batch(req: BatchRequest):
    n = run_batch(req.since_ts, req.limit)
    return {"processed": n}

@app.post("/predict-last-week")
def predict_last_week():
    n = run_batch(None, int(os.getenv("BATCH_LIMIT","500")))
    return {"processed": n}

def insert_weekly_rollup():
    ddl = """
    CREATE TABLE IF NOT EXISTS ripeness_weekly_rollups_ts (
      id BIGSERIAL PRIMARY KEY,
      ts TIMESTAMPTZ NOT NULL DEFAULT now(),  
      window_start TIMESTAMPTZ NOT NULL,
      window_end   TIMESTAMPTZ NOT NULL,
      fruit_type TEXT NOT NULL,
      cnt_total  INTEGER NOT NULL,
      cnt_ripe   INTEGER NOT NULL,
      cnt_unripe INTEGER NOT NULL,
      cnt_rotten INTEGER NOT NULL,
      pct_ripe   DOUBLE PRECISION NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_rwrt_ts ON ripeness_weekly_rollups_ts(ts);
    CREATE INDEX IF NOT EXISTS ix_rwrt_fruit_ts ON ripeness_weekly_rollups_ts(fruit_type, ts);
    """
    sql = """
    WITH w AS (
      SELECT now() - interval '7 days' AS ws, now() AS we
    ),
    agg AS (
      SELECT
        il.fruit_type,
        COUNT(*) AS cnt_total,
        SUM(CASE WHEN rp.ripeness_label='ripe'   THEN 1 ELSE 0 END) AS cnt_ripe,
        SUM(CASE WHEN rp.ripeness_label='unripe' THEN 1 ELSE 0 END) AS cnt_unripe,
        SUM(CASE WHEN rp.ripeness_label='rotten' THEN 1 ELSE 0 END) AS cnt_rotten
      FROM ripeness_predictions rp
      JOIN inference_logs il ON il.id = rp.inference_log_id
      JOIN w ON rp.ts >= w.ws AND rp.ts < w.we
      GROUP BY il.fruit_type
    )
    INSERT INTO ripeness_weekly_rollups_ts
      (ts, window_start, window_end, fruit_type, cnt_total, cnt_ripe, cnt_unripe, cnt_rotten, pct_ripe)
    SELECT
      now(), (SELECT ws FROM w), (SELECT we FROM w),
      fruit_type, cnt_total, cnt_ripe, cnt_unripe, cnt_rotten,
      CASE WHEN cnt_total>0 THEN cnt_ripe::double precision/cnt_total ELSE 0 END
    FROM agg;
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(ddl)
        cur.execute(sql)
    return True


@app.post("/rollup/weekly")
def rollup_weekly():
    insert_weekly_rollup()
    return {"ok": True}
