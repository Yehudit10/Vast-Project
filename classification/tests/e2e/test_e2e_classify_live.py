"""
E2E (live) test for scripts/classify.py with a real Postgres database.

This test:
- Skips automatically if required environment variables are missing.
- Ensures a dedicated schema & minimal tables exist (idempotent).
- Generates two valid short WAV files (mono, 32kHz).
- Invokes classify.main() twice (one --audio per invocation) with --write-db and windowing flags that guarantee at least one window.
- Verifies in DB (within the target schema) that both files exist and have at least one aggregate row.
- Cleans up inserted rows (best-effort).

Required env:
  TEST_DB_URL        (e.g., postgresql://user:pass@host:5432/db)
  TEST_CHECKPOINT    (path to a valid checkpoint expected by classify.py)

Optional env:
  TEST_DB_SCHEMA     (default: audio_cls)
  TEST_HEAD          (path to trained head.joblib)
  TEST_LABELS_CSV    (path to labels csv)
  TEST_DEVICE        (default: cpu)

Marker:
  @pytest.mark.e2e_live
"""

import os
import time
import wave
import struct
import math
from pathlib import Path
from typing import List, Tuple

import pytest
import psycopg2
import psycopg2.extras
import numpy as np

# Import the CLI module under test (assuming PYTHONPATH points to classification/)
from scripts import classify as CL


pytestmark = pytest.mark.e2e_live


# ----------------------- helpers -----------------------

def _env_or_skip():
    db_url = os.getenv("TEST_DB_URL", "").strip()
    ckpt   = os.getenv("TEST_CHECKPOINT", "").strip()
    if not db_url or not ckpt:
        pytest.skip("Missing TEST_DB_URL or TEST_CHECKPOINT; skipping e2e_live test.")
    schema     = os.getenv("TEST_DB_SCHEMA", "audio_cls").strip() or "audio_cls"
    head       = os.getenv("TEST_HEAD", "").strip() or None
    labels_csv = os.getenv("TEST_LABELS_CSV", "").strip() or None
    device     = os.getenv("TEST_DEVICE", "cpu").strip() or "cpu"
    return db_url, schema, ckpt, head, labels_csv, device


def _write_sine_wav(path: Path, sr: int = 32000, freq: float = 440.0, duration_s: float = 0.5, amplitude: float = 0.3):
    """Write a small mono WAV with a sine tone (16-bit PCM)."""
    n_frames = int(sr * duration_s)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        n_channels = 1
        sampwidth = 2  # 16-bit
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sr)
        for i in range(n_frames):
            sample = amplitude * math.sin(2.0 * math.pi * freq * (i / sr))
            val = max(-1.0, min(1.0, sample))
            wf.writeframes(struct.pack("<h", int(val * 32767)))


def _prepare_schema_and_tables(db_url: str, schema: str):
    """Ensure target schema exists and minimal tables required by db_io_pg exist, then set search_path."""
    ddl = f"""
    CREATE SCHEMA IF NOT EXISTS {schema};

    SET search_path TO {schema}, public;

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
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
    finally:
        conn.close()


def _set_search_path(conn, schema: str):
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema}, public;")
    conn.commit()


def _run_classify_once(audio_path: Path, checkpoint: Path, db_url: str, db_schema: str,
                       device: str, head: str = None, labels_csv: str = None):
    """
    Invoke scripts.classify.main() for a single audio file with --write-db.
    We pass windowing flags that guarantee at least one window for a 0.5s clip.
    """
    argv = [
        "classify.py",
        "--audio", str(audio_path),
        "--checkpoint", str(checkpoint),
        "--device", device,
        "--write-db",
        "--db-url", db_url,
        "--db-schema", db_schema,
        "--window-sec", "0.5",
        "--hop-sec", "0.5",
        "--pad-last",
    ]
    if head:
        argv += ["--head", head]
    if labels_csv:
        argv += ["--labels-csv", labels_csv]

    CL.sys.argv = argv
    CL.main()


def _select_file_and_aggs(conn, schema: str, path: str) -> Tuple[int, list]:
    """
    Fetch (file_id, aggregates_rows) for a given file path from the target schema.
    Returns: (file_id, [rows]) where rows = list of tuples
    """
    _set_search_path(conn, schema)
    with conn.cursor() as cur:
        cur.execute("SELECT file_id FROM files WHERE path = %s", (path,))
        row = cur.fetchone()
        if not row:
            return -1, []
        file_id = int(row[0])
        cur.execute("SELECT run_id, head_p_animal, head_p_vehicle, head_p_shotgun, head_p_other, num_windows, agg_mode "
                    "FROM file_aggregates WHERE file_id = %s", (file_id,))
        aggs = cur.fetchall() or []
        return file_id, aggs


def _cleanup_db_rows(conn, schema: str, paths: List[str]):
    """Best-effort cleanup inside the target schema: delete aggregates first, then files."""
    _set_search_path(conn, schema)
    try:
        with conn.cursor() as cur:
            for p in paths:
                cur.execute("SELECT file_id FROM files WHERE path = %s", (p,))
                r = cur.fetchone()
                if r:
                    fid = int(r[0])
                    cur.execute("DELETE FROM file_aggregates WHERE file_id = %s", (fid,))
                    cur.execute("DELETE FROM files WHERE file_id = %s", (fid,))
        conn.commit()
    except Exception:
        conn.rollback()


# ----------------------- the E2E test -----------------------

def test_e2e_classify_writes_and_reads_from_db(tmp_path):
    db_url, schema, ckpt, head, labels_csv, device = _env_or_skip()

    # Ensure schema & tables exist (independent of any existing 'public.files' structure)
    _prepare_schema_and_tables(db_url, schema)

    # Prepare two WAVs
    wav1 = tmp_path / "e2e_a.wav"
    wav2 = tmp_path / "e2e_b.wav"
    _write_sine_wav(wav1, sr=32000, freq=330.0, duration_s=0.5)
    _write_sine_wav(wav2, sr=32000, freq=660.0, duration_s=0.5)

    # Run classify twice (one file per invocation) with windowing flags that guarantee windows
    _run_classify_once(wav1, Path(ckpt), db_url, schema, device, head=head, labels_csv=labels_csv)
    _run_classify_once(wav2, Path(ckpt), db_url, schema, device, head=head, labels_csv=labels_csv)

    # Optional settle
    time.sleep(0.1)

    # Verify in DB within our schema
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        f1_id, f1_aggs = _select_file_and_aggs(conn, schema, str(wav1))
        f2_id, f2_aggs = _select_file_and_aggs(conn, schema, str(wav2))

        assert f1_id > 0, "First file should be inserted into '<schema>.files'."
        assert f2_id > 0, "Second file should be inserted into '<schema>.files'."
        assert len(f1_aggs) >= 1, "First file should have at least one aggregate row."
        assert len(f2_aggs) >= 1, "Second file should have at least one aggregate row."

        # Optionally verify runs finished_at via run_ids present in aggregates
        run_ids = {r[0] for r in (f1_aggs + f2_aggs) if r and r[0]}
        if run_ids:
            _set_search_path(conn, schema)
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM runs WHERE run_id = ANY(%s) AND finished_at IS NOT NULL",
                            (list(run_ids),))
                cnt = cur.fetchone()[0]
                assert cnt >= 1, "At least one run should be marked finished."
        conn.commit()
    finally:
        # Best-effort cleanup of inserted rows (keep runs for history)
        _cleanup_db_rows(conn, schema, [str(wav1), str(wav2)])
        conn.close()
