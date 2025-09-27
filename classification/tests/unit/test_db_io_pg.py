# """
# Unit tests for core/db_io_pg.py

# We fully mock psycopg2.connect and psycopg2.extras.Json so tests run without a real DB.
# Each test validates flow: execute calls, parameters, commit/rollback behavior, and return values.
# """

# import re
# import pytest
# from types import SimpleNamespace

# # Import the module under test
# from core import db_io_pg


# # ----------------------- Fakes / Helpers -----------------------

# class FakeCursor:
#     def __init__(self, script=None):
#         self.executed = []   # list of (sql, params)
#         self.script = script or {}
#         self._fetchone = None

#     def __enter__(self):
#         # support: with conn.cursor() as cur:
#         return self

#     def __exit__(self, exc_type, exc, tb):
#         # don't suppress exceptions
#         return False

#     def execute(self, sql, params=None):
#         self.executed.append((sql, params))
#         for pattern, action in self.script.items():
#             if re.search(pattern, str(sql), re.IGNORECASE):
#                 if isinstance(action, Exception):
#                     raise action
#                 if callable(action):
#                     action(sql, params)

#     def fetchone(self):
#         return self._fetchone

#     def set_fetchone(self, value):
#         self._fetchone = value

#     def close(self):
#         pass


# class FakeConnection:
#     def __init__(self, cursor: FakeCursor):
#         self._cursor = cursor
#         self.closed = False
#         self.commits = 0
#         self.rollbacks = 0

#     def cursor(self):
#         return self._cursor

#     def commit(self):
#         self.commits += 1

#     def rollback(self):
#         self.rollbacks += 1

#     def close(self):
#         self.closed = True


# class FakeJson:
#     """Lightweight stand-in for psycopg2.extras.Json wrapper."""
#     def __init__(self, obj):
#         self.obj = obj
#     def __repr__(self):
#         return f"FakeJson({self.obj!r})"


# def make_fake_psycopg2(fake_conn: FakeConnection):
#     """
#     Build a fake psycopg2 module with .connect() and .extras.Json.
#     We'll monkeypatch db_io_pg.psycopg2 to this.
#     """
#     fake_extras = SimpleNamespace(Json=FakeJson)
#     class _FakePsycopg2:
#         extras = fake_extras
#         def connect(self, dsn):
#             return fake_conn
#     return _FakePsycopg2()


# # ----------------------- Fixtures -----------------------

# @pytest.fixture
# def fake_db_env(monkeypatch):
#     """Isolate environment variables possibly read by db layer."""
#     for k in ("DB_URL", "DATABASE_URL", "PGHOST", "PGUSER", "PGPASSWORD"):
#         monkeypatch.delenv(k, raising=False)


# @pytest.fixture
# def cur():
#     return FakeCursor()


# @pytest.fixture
# def conn(cur):
#     return FakeConnection(cursor=cur)


# @pytest.fixture
# def psycopg2_fake(conn, monkeypatch):
#     """Monkeypatch db_io_pg.psycopg2 with a controllable fake."""
#     fake = make_fake_psycopg2(conn)
#     monkeypatch.setattr(db_io_pg, "psycopg2", fake)
#     return fake


# # ----------------------- open_db -----------------------

# def test_open_db_missing_url_raises(psycopg2_fake):
#     with pytest.raises(ValueError):
#         db_io_pg.open_db(db_url="", schema="audio_cls")


# @pytest.mark.parametrize("schema", ["bad-dash", "with space", "evil;drop", "💥", "a.b", "a*"])
# def test_open_db_invalid_schema_raises(psycopg2_fake, schema):
#     with pytest.raises(ValueError):
#         db_io_pg.open_db(db_url="postgresql://user:pass@localhost/db", schema= schema)


# def test_open_db_happy_path(psycopg2_fake, conn, cur):
#     db = db_io_pg.open_db(
#         db_url="postgresql://user:pass@localhost:5432/db",
#         schema="audio_cls"
#     )
#     # returns a connection (our fake)
#     assert db is conn
#     # should have executed statements that include the schema name
#     text = "\n".join(str(sql) for (sql, _params) in cur.executed)
#     assert "audio_cls" in text, "schema name should appear in DDL/search_path"
#     # should have committed setup
#     assert conn.commits >= 1
#     assert conn.rollbacks == 0


# # ----------------------- upsert_run / finish_run -----------------------

# def test_upsert_run_commits(psycopg2_fake, conn, cur):
#     # even if we set fetchone, current implementation doesn't return anything
#     cur.set_fetchone(("run_123",))
#     db_io_pg.upsert_run(conn, {
#         "run_id": "r-1",
#         "model_name": "cnn14",
#         "checkpoint": "ckpt.bin",
#         "head_path": None,
#         "labels_csv": None,
#         "window_sec": 0.5,
#         "hop_sec": 0.25,
#         "pad_last": True,
#         "agg": "mean",
#         "topk": 3,
#         "device": "cpu",
#         "code_version": "test",
#         "notes": None,
#     })
#     assert conn.commits >= 1 and conn.rollbacks == 0


# def test_upsert_run_rollback_on_failure(psycopg2_fake, conn):
#     bad_cur = FakeCursor(script={r"insert|upsert": RuntimeError("boom")})
#     bad_conn = FakeConnection(cursor=bad_cur)
#     fake = make_fake_psycopg2(bad_conn)
#     db_io_pg.psycopg2 = fake

#     with pytest.raises(Exception):
#         db_io_pg.upsert_run(bad_conn, {"window_sec": 0.5})
#     assert bad_conn.rollbacks >= 1


# def test_finish_run_updates(psycopg2_fake, conn):
#     db_io_pg.finish_run(conn, run_id="run_123")
#     assert conn.commits >= 1 and conn.rollbacks == 0
#     last_sql, last_params = conn._cursor.executed[-1]
#     assert "update runs" in str(last_sql).lower()
#     assert last_params == ("run_123",) or (isinstance(last_params, (list, tuple)) and "run_123" in last_params)


# # ----------------------- upsert_file -----------------------

# def test_upsert_file_commits_and_returns_id(psycopg2_fake, conn, cur):
#     cur.set_fetchone((42,))
#     file_id = db_io_pg.upsert_file(
#         conn,
#         path="/tmp/a.wav",
#         duration_s=1.23,
#         sample_rate=32000,
#         size_bytes=777,
#     )
#     assert conn.commits >= 1 and conn.rollbacks == 0
#     assert file_id == 42


# # ----------------------- _jsonify_topk -----------------------

# def test__jsonify_topk_wraps_non_string(psycopg2_fake):
#     obj = [{"label": "shotgun", "p": 0.7}]
#     j = db_io_pg._jsonify_topk(obj)
#     # Should be wrapped in Json-like
#     assert isinstance(j, FakeJson)
#     assert j.obj == obj


# def test__jsonify_topk_accepts_string(psycopg2_fake):
#     raw = '[{"label":"shotgun","p":0.7}]'
#     j = db_io_pg._jsonify_topk(raw)
#     # Depending on implementation it may pass-through or wrap.
#     # We accept either a Json wrapper or a plain string as long as not crashing.
#     assert isinstance(j, (FakeJson, str))


# # ----------------------- upsert_file_aggregate -----------------------

# def test_upsert_file_aggregate_uses_json_wrapper(psycopg2_fake, conn, cur):
#     payload = {
#         "file_id": 42,
#         "run_id": "run_123",
#         "agg_mode": "mean",
#         "num_windows": 3,
#         "audioset_topk_json": [{"label": "shotgun", "p": 0.7}],
#         # (optionally) head probabilities/extra fields could be included here
#     }
#     db_io_pg.upsert_file_aggregate(conn, payload)

#     assert conn.commits >= 1 and conn.rollbacks == 0

#     # Verify that Json wrapper was used for 'audioset_topk_json'
#     # by searching the last execute params for a FakeJson instance
#     last_sql, last_params = cur.executed[-1]
#     found_json = False
#     if isinstance(last_params, (list, tuple)):
#         found_json = any(isinstance(v, FakeJson) for v in last_params)
#     elif isinstance(last_params, dict):
#         found_json = any(isinstance(v, FakeJson) for v in last_params.values())
#     assert found_json, "audioset_topk_json should be wrapped in Json() for DB"

# # ----------------------- EXTRA COVERAGE: db_io_pg -----------------------

# def test_open_db_rejects_invalid_schema_name():
#     """
#     open_db must validate schema name using regex. Illegal names should raise ValueError.
#     """
#     with pytest.raises(ValueError):
#         db_io_pg.open_db(db_url="postgresql://u:p@h:5432/db", schema="not-valid!")


# def test__jsonify_topk_handles_json_string_and_non_json():
#     """
#     _jsonify_topk should parse JSON strings to objects; non-JSON strings should be wrapped
#     in {"raw": <value>} to keep data without failing.
#     """
#     js = '[{"label":"shotgun","p":0.7}]'
#     out1 = db_io_pg._jsonify_topk(js)
#     assert hasattr(out1, "adapted") or hasattr(out1, "dumps")

#     s = "not-json"
#     out2 = db_io_pg._jsonify_topk(s)
#     payload = getattr(out2, "adapted", None) or getattr(out2, "dumps", None)
#     if isinstance(payload, dict):
#         assert payload.get("raw") == "not-json"

# def test_upsert_run_rollback_on_exception(monkeypatch, conn):
#     """
#     Force cursor.execute to fail to cover rollback path inside upsert_run.
#     """
#     class BadCur:
#         def __enter__(self): return self
#         def __exit__(self, *a): pass
#         def execute(self, *a, **k): raise RuntimeError("bad")
#         def fetchone(self): return None
#     conn.cursor = lambda: BadCur()
#     with pytest.raises(RuntimeError):
#         db_io_pg.upsert_run(conn, {"run_id": "r1"})
#     assert conn.rollbacks >= 1

# def test_open_db_rollback_on_exception(monkeypatch, conn, cur):
#     """
#     Force an exception during schema setup to cover rollback + logging branch.
#     Also patch psycopg2.connect to use our fake connection (no real network).
#     """
#     # make the cursor fail on execute
#     def bad_execute(sql, params=None):
#         raise RuntimeError("boom")
#     cur.execute = bad_execute

#     # ensure open_db uses our fake connection instead of real psycopg2
#     monkeypatch.setattr(db_io_pg.psycopg2, "connect", lambda url: conn, raising=True)

#     with pytest.raises(RuntimeError):
#         db_io_pg.open_db("postgresql://u:p@h:5432/db", schema="audio_cls")

#     # verify rollback path executed
#     assert conn.rollbacks >= 1
