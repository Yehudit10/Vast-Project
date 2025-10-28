import psycopg
from pathlib import Path
from typing import List, Tuple, Optional

   
def dsn(pg):
    return f"host={pg['host']} port={pg['port']} dbname={pg['db']} user={pg['user']} password={pg['password']}"

def ensure_schema(con, schema_sql_path: Path):
    sql = Path(schema_sql_path).read_text(encoding="utf-8")
    with con.cursor() as cur:
        cur.execute("SET lock_timeout = '2s'; SET statement_timeout = '8s';")
        try:
            cur.execute(sql)
        except psycopg.errors.LockNotAvailable as e:
            print(f"[warn] lock timeout while applying {schema_sql_path}; skipping", flush=True)
        except Exception as e:
            print(f"[warn] failed to apply {schema_sql_path}: {e}", flush=True)

def insert_detection(cur, fruit_type, captured_at, source_path, feat, ripeness, flags):
    cur.execute(
        """
        INSERT INTO images (fruit_type, captured_at, source_path)
        VALUES (%s,%s,%s)
        ON CONFLICT (source_path) DO UPDATE
            SET fruit_type = EXCLUDED.fruit_type,
                captured_at = EXCLUDED.captured_at
        RETURNING image_id;
        """,
        (fruit_type, captured_at, source_path)
    )
    image_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO detections
           (image_id, mean_h, mean_s, mean_v, laplacian_var, brown_ratio, ripeness, quality_flags, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            image_id,
            feat.mean_h, feat.mean_s, feat.mean_v, 
            feat.lap_var, feat.brown_ratio, 
            ripeness, flags,captured_at
        ),
    )

def run_weekly_upsert(con, upsert_sql_path: Path):
    sql = Path(upsert_sql_path).read_text(encoding="utf-8")
    with con.cursor() as cur:
        cur.execute(sql)

def apply_sql_autocommit(dsn: str, sql_path):
    sql = Path(sql_path).read_text(encoding="utf-8")
    with psycopg.connect(dsn, autocommit=True) as cn:
        with cn.cursor() as cur:
            cur.execute("SET lock_timeout='2s'; SET statement_timeout='8s';")
            try:
                cur.execute(sql)
            except Exception as e:
                print(f"[warn] failed to apply {sql_path}: {e}", flush=True)

def fetch_inference_logs(pg: dict, lookback_days: int = 7,
                         fruit_filter: Optional[str] = None,
                         limit: Optional[int] = None) -> List[Tuple[str, str]]:
    """
    Returns [(fruit_type, image_url), ...] from the last N days.
    """
    sql_parts = [
        "SELECT fruit_type, image_url",
        "FROM inference_logs",
        "WHERE ts >= NOW() - make_interval(days => %s)"
    ]
    params = [lookback_days]

    if fruit_filter:
        sql_parts.append("AND fruit_type = %s")
        params.append(fruit_filter)

    sql_parts.append("ORDER BY ts DESC")
    if limit:
        sql_parts.append(f"LIMIT {int(limit)}")

    sql = " ".join(sql_parts)

    with psycopg.connect(dsn(pg)) as con:
        with con.cursor() as cur:
            cur.execute(sql, params)
            return [(r[0], r[1]) for r in cur.fetchall()]
