import os
import psycopg2
from psycopg2 import sql
from typing import Optional

FILES_SCHEMA = os.getenv("FILES_SCHEMA", "public")
FILES_TABLE  = os.getenv("FILES_TABLE", "sound_new_sounds_connections")

def _files_table_ql() -> sql.SQL:
    return sql.SQL("{}.{}").format(sql.Identifier(FILES_SCHEMA), sql.Identifier(FILES_TABLE))

_KEY_COL = sql.Identifier("key")

def open_db():
    host = os.getenv("DB_HOST", "postgres")
    port = int(os.getenv("DB_PORT", "5432"))
    db   = os.getenv("DB_NAME", "missions_db")
    user = os.getenv("DB_USER", "missions_user")
    pwd  = os.getenv("DB_PASSWORD", "pg123")
    schema = os.getenv("DB_SCHEMA", "agcloud_audio")

    conn = psycopg2.connect(host=host, port=port, dbname=db, user=user, password=pwd)
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SET search_path TO {}, public;").format(sql.Identifier(schema)))
    return conn

def ensure_file(conn, *, bucket: str, object_key: str,
                size_bytes: Optional[int] = None,
                sample_rate: Optional[int] = None,
                duration_s: Optional[float] = None) -> int:
    """Idempotent ensure in public.sound_new_sounds_connections by (bucket, object_key)."""
    combined_key = f"{bucket}/{object_key}".lstrip("/")
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT id FROM {} WHERE {} = %s")
                   .format(_files_table_ql(),_KEY_COL),
                (combined_key,),
            )
            row = cur.fetchone()
            if row:
                return int(row[0])

            cur.execute(
                sql.SQL("""
                    INSERT INTO {} ({}, size_bytes, sample_rate, duration_s)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """).format(_files_table_ql(), _KEY_COL),
                (combined_key, size_bytes, sample_rate, duration_s),
            )
            new_id = cur.fetchone()[0]

        conn.commit()
        return int(new_id)
    except Exception:
        conn.rollback()
        raise

def ensure_run(conn, run_id: str):
    """
    Ensure there is a row in agcloud_audio.runs for FK constraints.
    This will INSERT ... ON CONFLICT DO NOTHING with reasonable defaults.
    """
    import os
    window_sec = float(os.getenv("WINDOW_SEC", "2.0"))
    hop_sec    = float(os.getenv("HOP_SEC", "0.5"))
    pad_last   = os.getenv("PAD_LAST", "true").lower() in ("1", "true", "yes", "on")

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
            "head_path": os.getenv("HEAD", ""),
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
    """Select-only (NO insert). Raises ValueError if not found."""
    with conn.cursor() as cur:
        if file_id is not None:
            cur.execute(
                sql.SQL("SELECT id FROM {} WHERE id = %s").format(_files_table_ql()),
                (file_id,),
            )
            row = cur.fetchone()
            if row:
                return int(row[0])
            raise ValueError(f"id {file_id} not found in {FILES_SCHEMA}.{FILES_TABLE}")

        if bucket is not None and object_key is not None:
            combined_key = f"{bucket}/{object_key}".lstrip("/")
            cur.execute(
                sql.SQL("SELECT id FROM {} WHERE {} = %s")
                   .format(_files_table_ql(), _KEY_COL),
                (combined_key,),
            )
            row = cur.fetchone()
            if row:
                return int(row[0])
            raise ValueError(f"File s3://{bucket}/{object_key} not found in {FILES_SCHEMA}.{FILES_TABLE}")

        raise ValueError("Must provide file_id or (bucket, object_key)")
