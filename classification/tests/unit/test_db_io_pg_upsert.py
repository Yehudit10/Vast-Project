"""
Unit tests for core/db_io_pg.py – upsert_run, finish_run, upsert_file
"""

import pytest
from core import db_io_pg

def test_upsert_run_commits(psycopg2_fake, conn, cur):
    cur.set_fetchone(("run_123",))
    db_io_pg.upsert_run(conn, {
        "run_id": "r-1",
        "model_name": "cnn14",
        "checkpoint": "ckpt.bin",
        "head_path": None,
        "labels_csv": None,
        "window_sec": 0.5,
        "hop_sec": 0.25,
        "pad_last": True,
        "agg": "mean",
        "topk": 3,
        "device": "cpu",
        "code_version": "test",
        "notes": None,
    })
    assert conn.commits >= 1 and conn.rollbacks == 0


def test_upsert_run_rollback_on_failure(psycopg2_fake, conn):
    from types import SimpleNamespace
    import re

    class BadCur:
        def __init__(self):
            self.executed = []
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params=None): raise RuntimeError("boom")
        def fetchone(self): return None

    bad_conn = conn
    bad_conn.cursor = lambda: BadCur()
    with pytest.raises(RuntimeError):
        db_io_pg.upsert_run(bad_conn, {"window_sec": 0.5})
    assert bad_conn.rollbacks >= 1


def test_finish_run_updates(psycopg2_fake, conn):
    db_io_pg.finish_run(conn, run_id="run_123")
    assert conn.commits >= 1 and conn.rollbacks == 0
    last_sql, last_params = conn._cursor.executed[-1]
    assert "update runs" in str(last_sql).lower()
    assert last_params == ("run_123",) or (isinstance(last_params, (list, tuple)) and "run_123" in last_params)


def test_upsert_file_commits_and_returns_id(psycopg2_fake, conn, cur):
    cur.set_fetchone((42,))
    file_id = db_io_pg.upsert_file(
        conn,
        path="/tmp/a.wav",
        duration_s=1.23,
        sample_rate=32000,
        size_bytes=777,
    )
    assert conn.commits >= 1 and conn.rollbacks == 0
    assert file_id == 42


def test_upsert_run_rollback_on_exception(monkeypatch, conn):
    class BadCur:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, *a, **k): raise RuntimeError("bad")
        def fetchone(self): return None
    conn.cursor = lambda: BadCur()
    with pytest.raises(RuntimeError):
        db_io_pg.upsert_run(conn, {"run_id": "r1"})
    assert conn.rollbacks >= 1
