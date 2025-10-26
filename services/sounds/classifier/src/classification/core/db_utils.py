# File: classification/core/db_utils.py
import os
import psycopg2
from psycopg2 import sql
from typing import Optional

def open_db():
    """
    Open a PostgreSQL connection using env vars and set search_path to DB_SCHEMA,public.
    """
    host = os.getenv("DB_HOST", "postgres")
    port = int(os.getenv("DB_PORT", "5432"))
    db   = os.getenv("DB_NAME", "missions_db")
    user = os.getenv("DB_USER", "missions_user")
    pwd  = os.getenv("DB_PASSWORD", "pg123")
    schema = os.getenv("DB_SCHEMA", "agcloud_audio")

    conn = psycopg2.connect(
        host=host, port=port, dbname=db, user=user, password=pwd
    )
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SET search_path TO {}, public;").format(sql.Identifier(schema)))
    return conn

def ensure_run(conn, run_id: str):
    """
    Ensure there is a row in agcloud_audio.runs for FK constraints.
    This will INSERT ... ON CONFLICT DO NOTHING with reasonable defaults.
    IMPORTANT: runs table has NOT NULL constraints on several fields.
    Adjust values if your runtime config differs.
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO runs (
                run_id, model_name, checkpoint, head_path, labels_csv,
                window_sec, hop_sec, pad_last, agg, topk, device, code_version, notes
            )
            VALUES (
                %(run_id)s, %(model_name)s, %(checkpoint)s, %(head_path)s, %(labels_csv)s,
                %(window_sec)s, %(hop_sec)s, %(pad_last)s, %(agg)s, %(topk)s, %(device)s,
                %(code_version)s, %(notes)s
            )
            ON CONFLICT (run_id) DO NOTHING
        """, {
            "run_id": run_id,
            "model_name": os.getenv("MODEL_NAME", "panns_cnn14"),
            "checkpoint": os.getenv("CHECKPOINT", "panns_cnn14.pth"),
            "head_path": os.getenv("SK_PIPELINE_PATH", ""),
            "labels_csv": os.getenv("LABELS_CSV", ""),
            "window_sec": float(os.getenv("WINDOW_SEC", "10")),
            "hop_sec": float(os.getenv("HOP_SEC", "10")),
            "pad_last": os.getenv("PAD_LAST", "false").lower() == "true",
            "agg": os.getenv("AGG", "mean"),
            "topk": int(os.getenv("TOPK", "3")),
            "device": os.getenv("DEVICE", "cpu"),
            "code_version": os.getenv("CODE_VERSION", ""),
            "notes": os.getenv("RUN_NOTES", "created by API ensure_run")
        })
    conn.commit()

def resolve_file_id(conn, *, file_id: Optional[int] = None,
                    bucket: Optional[str] = None, object_key: Optional[str] = None) -> int:
    """
    Resolve an existing file_id in public.files (NO insertion).
    Prefer file_id; else use (bucket, object_key).
    Raises ValueError if not found.
    """
    with conn.cursor() as cur:
        if file_id is not None:
            cur.execute("SELECT file_id FROM public.files WHERE file_id = %s", (file_id,))
            row = cur.fetchone()
            if row:
                return int(row[0])
            raise ValueError(f"file_id {file_id} not found in public.files")

        if bucket is not None and object_key is not None:
            cur.execute("""
                SELECT file_id FROM public.files
                WHERE bucket = %s AND object_key = %s
            """, (bucket, object_key))
            row = cur.fetchone()
            if row:
                return int(row[0])
            raise ValueError(f"(bucket, object_key)=({bucket}, {object_key}) not found in public.files")

        raise ValueError("Must provide file_id or (bucket, object_key)")
