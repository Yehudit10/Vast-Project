# metrics_db/db.py
import os
from typing import Any, Dict, Optional
import psycopg2
from psycopg2.extensions import connection as PGConnection
from dotenv import load_dotenv


def _get_conn() -> PGConnection:
    """
    Open a PostgreSQL connection. No DDL here.
    Priority:
      1) DATABASE_URL
      2) discrete env vars (DB_HOST, DB_PORT, ...)
    """
    load_dotenv()

    dsn = (os.environ.get("DATABASE_URL") or "").strip()
    if dsn:
        return psycopg2.connect(dsn)

    host = os.environ.get("DB_HOST", "localhost")
    port = int(os.environ.get("DB_PORT", "5432"))
    name = os.environ.get("DB_NAME", "fruitdb")
    user = os.environ.get("DB_USER", "fruituser")
    password = os.environ.get("DB_PASSWORD", "fruitpass")
    sslmode = os.environ.get("DB_SSLMODE", "disable")  # prod: require/verify-full

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=name,
        user=user,
        password=password,
        sslmode=sslmode,
        application_name=os.environ.get("DB_APP_NAME", "metrics_service"),
        connect_timeout=int(os.environ.get("DB_CONNECT_TIMEOUT", "10")),
    )


def insert_training_run(rec: Dict[str, Any]) -> None:
    """
    Expects keys:
      backbone, image_size, num_epochs, train_split, top1_acc, best_top1_acc,
      artifacts_bucket, artifacts_prefix, labels_object, best_ckpt_object,
      metrics_object, cm_object, seed
    All columns must already exist in table training_runs.
    """
    sql = """
    INSERT INTO training_runs (
        backbone, image_size, num_epochs, train_split, top1_acc, best_top1_acc,
        artifacts_bucket, artifacts_prefix, labels_object, best_ckpt_object,
        metrics_object, cm_object, seed
    )
    VALUES (%(backbone)s, %(image_size)s, %(num_epochs)s, %(train_split)s,
            %(top1_acc)s, %(best_top1_acc)s, %(artifacts_bucket)s,
            %(artifacts_prefix)s, %(labels_object)s, %(best_ckpt_object)s,
            %(metrics_object)s, %(cm_object)s, %(seed)s)
    """
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, rec)
        conn.commit()


def insert_inference_log(
    *,
    model_backbone: str,
    image_size: int,
    fruit_type: str,
    score: float,
    latency_ms: Optional[float] = None,
    client_ip: Optional[str] = None,
    error: Optional[str] = None,
    image_url: Optional[str] = None,
) -> None:
    """
    Inserts a single inference log record. Table 'inference_logs' must exist.
    """
    sql = """
    INSERT INTO inference_logs (
        fruit_type, score, latency_ms, model_backbone, image_size,
        client_ip, error, image_url
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            sql,
            (
                fruit_type,
                score,
                latency_ms,
                model_backbone,
                image_size,
                client_ip,
                error,
                image_url,
            ),
        )
        conn.commit()


def db_healthcheck() -> bool:
    """Simple reachability check."""
    try:
        with _get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            return cur.fetchone() == (1,)
    except Exception:
        return False
