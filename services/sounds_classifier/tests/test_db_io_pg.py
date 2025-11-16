import json
import types
import pytest
import classification.core.db_io_pg as dbpg


# -------------------------
# Dummy connection helpers
# -------------------------

class DummyCursor:
    def __init__(self, rec=None, raise_on_execute=False):
        self.queries = []
        self._rec = rec
        self._raise = raise_on_execute
    def execute(self, q, p=None):
        if self._raise:
            raise RuntimeError("boom-exec")
        self.queries.append((q, p))
    def fetchone(self):
        return (123,)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False

class DummyConn:
    def __init__(self, raise_on_execute=False):
        self.cursors = []
        self.autocommit = False
        self._commits = 0
        self._rollbacks = 0
        self._raise = raise_on_execute
    def cursor(self):
        c = DummyCursor(raise_on_execute=self._raise)
        self.cursors.append(c)
        return c
    def commit(self):
        self._commits += 1
    def rollback(self):
        self._rollbacks += 1


# -------------------------
# open_db
# -------------------------

def test_open_db_validates_and_initializes_schema(monkeypatch):
    # make psycopg2.connect return our dummy connection
    monkeypatch.setattr(dbpg.psycopg2, "connect", lambda url: DummyConn())
    conn = dbpg.open_db("postgresql://u:p@h:5432/db", schema="audio_cls")
    assert isinstance(conn, DummyConn)
    # schema init should have committed once
    assert conn._commits >= 1

def test_open_db_rejects_bad_schema():
    with pytest.raises(ValueError):
        dbpg.open_db("postgresql://u:p@h:5432/db", schema="bad-dash")

def test_open_db_rollback_on_failure(monkeypatch):
    # first cursor.execute will raise
    monkeypatch.setattr(dbpg.psycopg2, "connect", lambda url: DummyConn(raise_on_execute=True))
    with pytest.raises(RuntimeError):
        dbpg.open_db("postgresql://u:p@h:5432/db", schema="audio_cls")


# -------------------------
# upsert_run
# -------------------------

def test_upsert_run_success(monkeypatch):
    conn = DummyConn()
    dbpg.upsert_run(conn, {
        "run_id": "r1", "model_name": "CNN14", "checkpoint": "ckpt",
        "head_path": "h", "labels_csv": "l", "window_sec": 2.0, "hop_sec": 0.5,
        "pad_last": True, "agg": "mean", "topk": 10, "device": "cpu",
        "code_version": "v", "notes": "n"
    })
    assert conn._commits == 1
    assert conn._rollbacks == 0
    # Ensure at least one execute has been issued
    assert conn.cursors and conn.cursors[0].queries

def test_upsert_run_rollback_on_exception(monkeypatch):
    conn = DummyConn(raise_on_execute=True)
    with pytest.raises(RuntimeError):
        dbpg.upsert_run(conn, {
            "run_id":"r1","model_name":"CNN14","checkpoint":"ckpt","head_path":"h","labels_csv":"l",
            "window_sec":2.0,"hop_sec":0.5,"pad_last":True,"agg":"mean","topk":10,"device":"cpu",
            "code_version":"v","notes":"n"
        })
    assert conn._rollbacks == 1
    assert conn._commits == 0


# -------------------------
# finish_run
# -------------------------

def test_finish_run_success():
    conn = DummyConn()
    dbpg.finish_run(conn, "r1")
    assert conn._commits == 1
    assert conn._rollbacks == 0
    assert conn.cursors[0].queries  # UPDATE executed

def test_finish_run_rollback_on_exception():
    conn = DummyConn(raise_on_execute=True)
    with pytest.raises(RuntimeError):
        dbpg.finish_run(conn, "r1")
    assert conn._rollbacks == 1
    assert conn._commits == 0

def test__jsonify_variants(monkeypatch):
    # Wrap psycopg2.extras.Json to observe value passed in
    captured = {"value": None}
    def fake_json(v):
        captured["value"] = v
        return ("JsonWrapped", v)

    monkeypatch.setattr(dbpg.psycopg2.extras, "Json", fake_json, raising=True)

    # string with valid JSON → parsed dict
    j = dbpg._jsonify('{"a":1}')
    assert j == ("JsonWrapped", {"a": 1})
    assert captured["value"] == {"a": 1}

    # plain string → {"raw": "..."}
    j2 = dbpg._jsonify("hello")
    assert j2 == ("JsonWrapped", {"raw": "hello"})
    assert captured["value"] == {"raw": "hello"}

    # dict passes through
    j3 = dbpg._jsonify({"k": 3})
    assert j3 == ("JsonWrapped", {"k": 3})
    assert captured["value"] == {"k": 3}

def test_upsert_file_aggregate_success(monkeypatch):
    # Make Json a pass-through so psycopg2.extras.Json(v) -> v
    monkeypatch.setattr(dbpg.psycopg2.extras, "Json", lambda x: x, raising=True)

    conn = DummyConn()
    dbpg.upsert_file_aggregate(conn, {
        "run_id":"r1","file_id":123,
        "head_probs_json":{"car":0.9},"head_pred_label":"car","head_pred_prob":0.9,
        "head_unknown_threshold":0.55,"head_is_another":False,
        "num_windows":3,"agg_mode":"mean","processing_ms":123
    })
    assert conn._commits == 1
    assert conn._rollbacks == 0

def test_upsert_file_aggregate_accepts_string_json_and_rollback_on_exception(monkeypatch):
    # Json wrapper
    monkeypatch.setattr(dbpg.psycopg2.extras, "Json", lambda x: x, raising=True)

    # connection that will fail during execute
    conn = DummyConn(raise_on_execute=True)
    with pytest.raises(RuntimeError):
        dbpg.upsert_file_aggregate(conn, {
            "run_id":"r1","file_id":123,
            "head_probs_json":'{"car":0.9}',  # string json
            "head_pred_label":"car","head_pred_prob":0.9,
            "head_unknown_threshold":0.55,"head_is_another":False,
            "num_windows":3,"agg_mode":"mean","processing_ms":123
        })
    assert conn._rollbacks == 1
    assert conn._commits == 0
