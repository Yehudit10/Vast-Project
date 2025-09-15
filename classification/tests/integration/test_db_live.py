"""
Live Postgres integration for core/db_io_pg.py.

Requirements:
- Environment variable TEST_DB_URL must be set (e.g., postgresql://user:pass@host:port/db)
- Optional TEST_DB_SCHEMA (defaults to 'audio_cls')

This test:
1) Opens DB and sets schema.
2) Ensures minimal tables exist (idempotent DDL).
3) Inserts run/file/aggregate using real functions.
4) Verifies rows via SELECT.
5) Cleans up.

Mark: integration_db
"""

import os
import time
import uuid
import pytest

from core import db_io_pg


pytestmark = pytest.mark.integration_db


def _env_or_skip():
    url = os.getenv("TEST_DB_URL", "").strip()
    if not url:
        pytest.skip("TEST_DB_URL not set; skipping live-db integration test")
    schema = os.getenv("TEST_DB_SCHEMA", "audio_cls").strip() or "audio_cls"
    return url, schema


def _ensure_tables(conn):
    """
    Create minimal tables used by db_io_pg with columns referenced in its SQL.
    Idempotent via IF NOT EXISTS + unique constraints used by upsert statements.
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS runs (
        run_id         TEXT PRIMARY KEY,
        model_name     TEXT,
        checkpoint     TEXT,
        head_path      TEXT,
        labels_csv     TEXT,
        window_sec     DOUBLE PRECISION,
        hop_sec        DOUBLE PRECISION,
        pad_last       BOOLEAN,
        agg            TEXT,
        topk           INTEGER,
        device         TEXT,
        code_version   TEXT,
        notes          TEXT,
        created_at     TIMESTAMPTZ DEFAULT now(),
        finished_at    TIMESTAMPTZ
    );

    CREATE TABLE IF NOT EXISTS files (
        file_id      SERIAL PRIMARY KEY,
        path         TEXT UNIQUE NOT NULL,
        duration_s   DOUBLE PRECISION,
        sample_rate  INTEGER,
        size_bytes   BIGINT
    );

    CREATE TABLE IF NOT EXISTS file_aggregates (
        run_id              TEXT NOT NULL,
        file_id             INTEGER NOT NULL,
        audioset_topk_json  JSONB,
        head_p_animal       REAL,
        head_p_vehicle      REAL,
        head_p_shotgun      REAL,
        head_p_other        REAL,
        num_windows         INTEGER,
        agg_mode            TEXT,
        PRIMARY KEY (run_id, file_id),
        FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
        FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE
    );
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def test_live_db_flow_end_to_end():
    db_url, schema = _env_or_skip()
    conn = db_io_pg.open_db(db_url=db_url, schema=schema)

    # Make sure required tables exist in the (now active) search_path schema
    _ensure_tables(conn)

    # --- test data (unique per run) ---
    run_id = f"it-{uuid.uuid4()}"
    file_path = f"/tmp/{run_id}.wav"

    try:
        # 1) upsert_run (no return value in current implementation)
        meta = {
            "run_id": run_id,
            "model_name": "cnn14",
            "checkpoint": "/models/cnn14.ckpt",
            "head_path": "/models/head.joblib",
            "labels_csv": None,
            "window_sec": 0.5,
            "hop_sec": 0.25,
            "pad_last": True,
            "agg": "mean",
            "topk": 3,
            "device": "cpu",
            "code_version": "it",
            "notes": "integration-test",
        }
        db_io_pg.upsert_run(conn, meta)

        # 2) upsert_file -> get file_id
        file_id = db_io_pg.upsert_file(
            conn,
            path=file_path,
            duration_s=1.23,
            sample_rate=32000,
            size_bytes=777,
        )
        assert isinstance(file_id, int) and file_id > 0

        # 3) upsert_file_aggregate
        row = {
            "run_id": run_id,
            "file_id": file_id,
            "audioset_topk_json": [{"label": "shotgun", "p": 0.7}, {"label": "animal", "p": 0.2}],
            "head_p_animal": 0.11,
            "head_p_vehicle": 0.22,
            "head_p_shotgun": 0.33,
            "head_p_other": 0.34,
            "num_windows": 3,
            "agg_mode": "mean",
        }
        db_io_pg.upsert_file_aggregate(conn, row)

        # 4) finish_run
        db_io_pg.finish_run(conn, run_id)

        # tiny settle (rarely needed on very slow disks)
        time.sleep(0.05)

        # --- verify via SELECT ---
        with conn.cursor() as cur:
            cur.execute("SELECT run_id, finished_at FROM runs WHERE run_id = %s", (run_id,))
            r = cur.fetchone()
            assert r is not None and r[0] == run_id and r[1] is not None

            cur.execute("SELECT file_id, path, sample_rate FROM files WHERE file_id = %s", (file_id,))
            f = cur.fetchone()
            assert f is not None and f[0] == file_id and f[1] == file_path and f[2] == 32000

            cur.execute("SELECT head_p_shotgun, num_windows, agg_mode, audioset_topk_json "
                        "FROM file_aggregates WHERE run_id=%s AND file_id=%s", (run_id, file_id))
            a = cur.fetchone()
            assert a is not None
            assert abs(float(a[0]) - 0.33) < 1e-6
            assert a[1] == 3 and a[2] == "mean"
            # jsonb presence (no deep compare to keep DB-dialect-agnostic)
            assert a[3] is not None
    finally:
        # --- cleanup (best-effort) ---
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM file_aggregates WHERE run_id = %s", (run_id,))
                cur.execute("DELETE FROM files WHERE path = %s", (file_path,))
                cur.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()
