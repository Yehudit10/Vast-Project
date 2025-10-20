# # inference/db_writer.py
# import os
# from dotenv import load_dotenv
# import psycopg2
# from psycopg2.extras import Json, RealDictCursor

# load_dotenv()  # קורא .env בשורש הפרויקט אם קיים

# PG_HOST = os.getenv("PG_HOST", os.getenv("PGHOST", "localhost"))
# PG_PORT = int(os.getenv("PG_PORT", os.getenv("PGPORT", 5432)))
# PG_USER = os.getenv("PG_USER", os.getenv("POSTGRES_USER", "missions_user"))
# PG_PASSWORD = os.getenv("PG_PASSWORD", os.getenv("POSTGRES_PASSWORD", "pg123"))
# PG_DATABASE = os.getenv("PG_DATABASE", os.getenv("POSTGRES_DB", "missions_db"))

# def get_conn():
#     conn = psycopg2.connect(
#         host=PG_HOST,
#         port=PG_PORT,
#         user=PG_USER,
#         password=PG_PASSWORD,
#         dbname=PG_DATABASE,
#     )
#     return conn

# def insert_result(fruit_id: str, status: str, defect_type: str = None,
#                   severity: float = None, metrics: dict = None, latency_ms: float = None):
#     metrics = metrics or {}
#     conn = get_conn()
#     try:
#         with conn:
#             with conn.cursor(cursor_factory=RealDictCursor) as cur:
#                 cur.execute("""
#                     INSERT INTO public.fruit_defect_results
#                       (fruit_id, status, defect_type, severity, metrics, latency_ms)
#                     VALUES (%s, %s, %s, %s, %s, %s)
#                     RETURNING id, created_at;
#                 """, (fruit_id, status, defect_type, severity, Json(metrics), latency_ms))
#                 row = cur.fetchone()
#                 return row
#     finally:
#         conn.close()


# inference/db_writer.py
import os
import time
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import Json, RealDictCursor

load_dotenv()  # קורא .env אם קיים

# --- פרטי חיבור ל-Postgres ---
PG_HOST = os.getenv("PG_HOST", os.getenv("PGHOST", "localhost"))
PG_PORT = int(os.getenv("PG_PORT", os.getenv("PGPORT", 5432)))
PG_USER = os.getenv("PG_USER", os.getenv("POSTGRES_USER", "missions_user"))
PG_PASSWORD = os.getenv("PG_PASSWORD", os.getenv("POSTGRES_PASSWORD", "pg123"))
PG_DATABASE = os.getenv("PG_DATABASE", os.getenv("POSTGRES_DB", "missions_db"))

# --- פונקציה לחיבור ---
def get_conn():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DATABASE,
    )

# --- הכנסת רשומה אחת לטבלה ---
def insert_result(fruit_id: str, status: str, defect_type: str = None,
                  severity: float = None, metrics: dict = None, latency_ms: float = None):
    metrics = metrics or {}
    conn = get_conn()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO public.fruit_defect_results
                      (fruit_id, status, defect_type, severity, metrics, latency_ms, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                    RETURNING id, created_at;
                """, (fruit_id, status, defect_type, severity, Json(metrics), latency_ms))
                row = cur.fetchone()
                return row
    finally:
        conn.close()

# --- פונקציה לקבלת payload של inference ולהכניס כל תוצאה לטבלה ---
def write_results_to_db(payload: dict):
    """
    Expects payload = {
        "summary": {...},
        "results": [
            {"image": str, "status": str, "confidence": float, "prob_defect": float, "latency_ms_model": float},
            ...
        ]
    }
    """
    results = payload.get("results", [])
    inserted = 0
    for r in results:
        fruit_id = r.get("image")
        status = r.get("status")
        latency = r.get("latency_ms_model")
        metrics = {"prob_defect": r.get("prob_defect"), "confidence": r.get("confidence")}
        try:
            insert_result(fruit_id=fruit_id, status=status, metrics=metrics, latency_ms=latency)
            inserted += 1
        except Exception as e:
            print(f"[WARNING] Failed to insert {fruit_id} into DB: {e}")
    print(f"[INFO] Inserted {inserted}/{len(results)} records into Postgres")
