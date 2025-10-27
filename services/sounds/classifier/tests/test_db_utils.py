# File: tests/test_db_utils.py
import os
import re
import pytest

import classification.core.db_utils as dbu

# -----------------------------
# Fake psycopg2 connection/cursor
# -----------------------------
class FakeCursor:
    def __init__(self, script_recorder):
        self.script_recorder = script_recorder
        self._fetchone = None  # single value returned by fetchone()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        # Record statements and params for later assertions
        self.script_recorder.append(("EXEC", str(query), params))

    def fetchone(self):
        return self._fetchone

    # helper for tests to set what fetchone should return
    def set_fetchone(self, value):
        self._fetchone = value


class FakeConn:
    def __init__(self):
        self.autocommit = False
        self.closed = False
        self._script = []
        self._cursor = FakeCursor(self._script)

    def cursor(self):
        return self._cursor

    def commit(self):
        self._script.append(("COMMIT", None, None))

    def rollback(self):
        self._script.append(("ROLLBACK", None, None))

    def close(self):
        self.closed = True

    # test helper
    def script(self):
        return list(self._script)


# -----------------------------
# Fixture
# -----------------------------
@pytest.fixture
def fake_conn(monkeypatch):
    """
    Patch psycopg2.connect to return our FakeConn.
    Also ensure env vars exist with harmless defaults.
    """
    fc = FakeConn()

    def fake_connect(**kwargs):
        return fc

    # Patch psycopg2.connect inside db_utils module
    monkeypatch.setattr(dbu.psycopg2, "connect", fake_connect)

    # Minimal env for db_utils.open_db()
    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "missions_db")
    monkeypatch.setenv("DB_USER", "missions_user")
    monkeypatch.setenv("DB_PASSWORD", "pg123")
    monkeypatch.setenv("DB_SCHEMA", "agcloud_audio")

    return fc


# -----------------------------
# Tests for open_db()
# -----------------------------
def test_open_db_sets_search_path(fake_conn):
    conn = dbu.open_db()
    assert conn is fake_conn
    # We expect one SET search_path statement with our schema
    script = conn.script()
    execs = [s for s in script if s[0] == "EXEC"]
    assert any(
        ("SET search_path TO" in q) and ("agcloud_audio" in q)
        for _, q, _ in execs
    ), f"Expected SET search_path to agcloud_audio, got: {execs}"
    # autocommit should remain False
    assert conn.autocommit is False


# -----------------------------
# Tests for ensure_run()
# -----------------------------
def test_ensure_run_inserts_and_commits(fake_conn, monkeypatch):
    # Provide env to fill NOT NULL columns
    monkeypatch.setenv("MODEL_NAME", "panns_cnn14")
    monkeypatch.setenv("CHECKPOINT", "ckpt.pth")
    monkeypatch.setenv("SK_PIPELINE_PATH", "/tmp/head.joblib")
    monkeypatch.setenv("LABELS_CSV", "")
    monkeypatch.setenv("WINDOW_SEC", "10")
    monkeypatch.setenv("HOP_SEC", "10")
    monkeypatch.setenv("PAD_LAST", "true")
    monkeypatch.setenv("AGG", "mean")
    monkeypatch.setenv("TOPK", "3")
    monkeypatch.setenv("DEVICE", "cpu")
    monkeypatch.setenv("CODE_VERSION", "test")
    monkeypatch.setenv("RUN_NOTES", "unit-test")

    dbu.ensure_run(fake_conn, run_id="run-123")
    # We expect one INSERT and one COMMIT
    script = fake_conn.script()
    insert_calls = [s for s in script if s[0] == "EXEC" and "INSERT INTO runs" in s[1]]
    assert len(insert_calls) == 1, f"expected single INSERT, got: {insert_calls}"
    assert ("COMMIT", None, None) in script


# -----------------------------
# Tests for resolve_file_id()
# -----------------------------
def test_resolve_file_id_by_file_id_ok(fake_conn):
    # Simulate existing file_id
    fake_conn._cursor.set_fetchone((42,))
    file_id = dbu.resolve_file_id(fake_conn, file_id=42)
    assert file_id == 42
    # Verify the WHERE clause by id appeared
    execs = [s for s in fake_conn.script() if s[0] == "EXEC"]
    assert any("WHERE file_id = %s" in q for _, q, _ in execs)

def test_resolve_file_id_by_file_id_not_found(fake_conn):
    fake_conn._cursor.set_fetchone(None)
    with pytest.raises(ValueError) as ex:
        dbu.resolve_file_id(fake_conn, file_id=999)
    assert "file_id 999 not found" in str(ex.value)

def test_resolve_file_id_by_bucket_key_ok(fake_conn):
    # Simulate a row found by (bucket, object_key)
    fake_conn._cursor.set_fetchone((321,))
    out = dbu.resolve_file_id(fake_conn, bucket="b", object_key="k")
    assert out == 321
    execs = [s for s in fake_conn.script() if s[0] == "EXEC"]
    assert any("WHERE bucket = %s AND object_key = %s" in q for _, q, _ in execs)

def test_resolve_file_id_by_bucket_key_not_found(fake_conn):
    fake_conn._cursor.set_fetchone(None)
    with pytest.raises(ValueError) as ex:
        dbu.resolve_file_id(fake_conn, bucket="b", object_key="k")
    msg = str(ex.value)
    # Be flexible about formatting: just assert key parts of the message exist
    assert "not found in public.files" in msg
    assert "s3://b/k" in msg or ("bucket" in msg and "object_key" in msg and "b" in msg and "k" in msg)
    
def test_resolve_file_id_requires_params(fake_conn):
    with pytest.raises(ValueError):
        dbu.resolve_file_id(fake_conn)  # neither file_id nor (bucket,key)


# # File: tests/test_db_utils.py
# import os
# import types
# import pytest

# import classification.core.db_utils as dbu
# from classification.core import db_utils

# # -----------------------------
# # Fake psycopg2 connection/cursor
# # -----------------------------
# class FakeCursor:
#     def __init__(self, script_recorder):
#         self.script_recorder = script_recorder
#         self._fetchone = None

#     def __enter__(self):
#         return self

#     def __exit__(self, exc_type, exc, tb):
#         return False

#     def execute(self, query, params=None):
#         # Record statements and params for later assertions
#         self.script_recorder.append(("EXEC", str(query), params))

#     def fetchone(self):
#         return self._fetchone

#     # helpers for tests to set what fetchone should return
#     def set_fetchone(self, value):
#         self._fetchone = value


# class FakeConn:
#     def __init__(self):
#         self.autocommit = False
#         self.closed = False
#         self._script = []
#         self._cursor = FakeCursor(self._script)

#     def cursor(self):
#         return self._cursor

#     def commit(self):
#         self._script.append(("COMMIT", None, None))

#     def rollback(self):
#         self._script.append(("ROLLBACK", None, None))

#     def close(self):
#         self.closed = True

#     # test helpers
#     def script(self):
#         return list(self._script)


# # -----------------------------
# # Fixtures
# # -----------------------------
# @pytest.fixture
# def fake_conn(monkeypatch):
#     """
#     Patch psycopg2.connect to return our FakeConn.
#     Also ensure env vars exist with harmless defaults.
#     """
#     fc = FakeConn()

#     def fake_connect(**kwargs):
#         # Allow both keyword connect and positional mapping
#         return fc

#     # Patch psycopg2.connect inside db_utils module
#     monkeypatch.setattr(dbu.psycopg2, "connect", fake_connect)

#     # Minimal env for db_utils.open_db()
#     monkeypatch.setenv("DB_HOST", "postgres")
#     monkeypatch.setenv("DB_PORT", "5432")
#     monkeypatch.setenv("DB_NAME", "missions_db")
#     monkeypatch.setenv("DB_USER", "missions_user")
#     monkeypatch.setenv("DB_PASSWORD", "pg123")
#     monkeypatch.setenv("DB_SCHEMA", "agcloud_audio")

#     return fc


# # -----------------------------
# # Tests for open_db()
# # -----------------------------
# def test_open_db_sets_search_path(fake_conn):
#     conn = dbu.open_db()
#     assert conn is fake_conn
#     # We expect one SET search_path and no CREATE SCHEMA here
#     script = conn.script()
#     # Ensure we executed a SET search_path statement with schema identifier
#     execs = [s for s in script if s[0] == "EXEC"]
#     assert any(
#         "SET search_path TO" in q and "agcloud_audio" in q for _, q, _ in execs
#     ), f"Expected SET search_path to agcloud_audio, got: {execs}"
#     # autocommit should remain False
#     assert conn.autocommit is False


# # -----------------------------
# # Tests for ensure_run()
# # -----------------------------
# def test_ensure_run_inserts_and_commits(fake_conn, monkeypatch):
#     # Provide some env to fill NOT NULL columns
#     monkeypatch.setenv("MODEL_NAME", "panns_cnn14")
#     monkeypatch.setenv("CHECKPOINT", "ckpt.pth")
#     monkeypatch.setenv("SK_PIPELINE_PATH", "/tmp/head.joblib")
#     monkeypatch.setenv("LABELS_CSV", "")
#     monkeypatch.setenv("WINDOW_SEC", "10")
#     monkeypatch.setenv("HOP_SEC", "10")
#     monkeypatch.setenv("PAD_LAST", "true")
#     monkeypatch.setenv("AGG", "mean")
#     monkeypatch.setenv("TOPK", "3")
#     monkeypatch.setenv("DEVICE", "cpu")
#     monkeypatch.setenv("CODE_VERSION", "test")
#     monkeypatch.setenv("RUN_NOTES", "unit-test")

#     dbu.ensure_run(fake_conn, run_id="run-123")
#     # We expect one INSERT and one COMMIT
#     script = fake_conn.script()
#     insert_calls = [s for s in script if s[0] == "EXEC" and "INSERT INTO runs" in s[1]]
#     assert len(insert_calls) == 1, f"expected single INSERT, got: {insert_calls}"
#     assert ("COMMIT", None, None) in script


# # -----------------------------
# # Tests for resolve_file_id()
# # -----------------------------
# def test_resolve_file_id_by_file_id_ok(fake_conn):
#     # set fetchone to simulate existing file_id
#     fake_conn._cursor.set_fetchone((42,))
#     file_id = dbu.resolve_file_id(fake_conn, file_id=42)
#     assert file_id == 42
#     # Verify correct query executed
#     execs = [s for s in fake_conn.script() if s[0] == "EXEC"]
#     assert any("FROM public.files WHERE file_id = %s" in q for _, q, _ in execs)

# def test_resolve_file_id_by_file_id_not_found(fake_conn):
#     # no fetchone result -> ValueError
#     fake_conn._cursor.set_fetchone(None)
#     with pytest.raises(ValueError) as ex:
#         dbu.resolve_file_id(fake_conn, file_id=999)
#     assert "not found" in str(ex.value)

# def test_resolve_file_id_by_bucket_key_ok(monkeypatch, fake_conn):
#     monkeypatch.setattr(
#         db_utils,
#         "ensure_file",
#         lambda conn, bucket, object_key, **kwargs: 123,
#         raising=True
#     )
#     out = db_utils.resolve_file_id(fake_conn, bucket="b", object_key="k")
#     assert out == 123
    
# # def test_resolve_file_id_by_bucket_key_not_found(fake_conn):
# #     fake_conn._cursor.set_fetchone(None)
# #     with pytest.raises(ValueError) as ex:
# #         dbu.resolve_file_id(fake_conn, bucket="imagery", object_key="missing.wav")
# #     assert "not found" in str(ex.value)

# def test_resolve_file_id_requires_params(fake_conn):
#     with pytest.raises(ValueError):
#         dbu.resolve_file_id(fake_conn)  # neither file_id nor (bucket,key)
