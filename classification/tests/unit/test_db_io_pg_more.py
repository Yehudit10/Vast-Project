# # tests/unit/test_db_io_pg_more.py
# import re
# import pytest
# from types import SimpleNamespace

# from core import db_io_pg


# class FakeCursor:
#     def __init__(self, boom=False):
#         self.executed = []
#         self.boom = boom
#     def __enter__(self): return self
#     def __exit__(self, *a): return False
#     def execute(self, sql, params=None):
#         self.executed.append((sql, params))
#         if self.boom:
#             raise RuntimeError("boom")
#     def fetchone(self): return (1,)

# class FakeConnection:
#     def __init__(self, cur):
#         self.cur = cur
#         self.commits = 0
#         self.rollbacks = 0
#     def cursor(self): return self.cur
#     def commit(self): self.commits += 1
#     def rollback(self): self.rollbacks += 1


# def test__jsonify_topk_invalid_json_string_wraps_raw(monkeypatch):
#     # Replace psycopg2.extras.Json with a recorder
#     captured = {}
#     class _Json:
#         def __init__(self, obj): captured["obj"] = obj
#     class FakeExtras: pass
#     FakeExtras.Json = _Json

#     fake_psycopg2 = SimpleNamespace(extras=FakeExtras)
#     monkeypatch.setattr(db_io_pg, "psycopg2", fake_psycopg2, raising=True)

#     j = db_io_pg._jsonify_topk("{not: json")
#     assert isinstance(j, _Json)
#     # Should be wrapped as {"raw": original_string}
#     assert captured["obj"] == {"raw": "{not: json"}


# def test_upsert_file_aggregate_rolls_back_on_failure(monkeypatch):
#     # Patch psycopg2.extras.Json -> identity passthrough
#     class _Json: 
#         def __init__(self, obj): self.obj = obj
#     fake_psycopg2 = SimpleNamespace(extras=SimpleNamespace(Json=_Json))
#     monkeypatch.setattr(db_io_pg, "psycopg2", fake_psycopg2, raising=True)

#     cur = FakeCursor(boom=True)  # force failure on execute
#     conn = FakeConnection(cur)

#     with pytest.raises(Exception):
#         db_io_pg.upsert_file_aggregate(conn, {
#             "run_id": "r", "file_id": 1, "audioset_topk_json": [{"label":"a","p":0.1}],
#             "head_p_animal": 0.1, "head_p_vehicle": 0.2, "head_p_shotgun": 0.3, "head_p_other": 0.4,
#             "num_windows": 1, "agg_mode": "mean",
#         })
#     assert conn.rollbacks == 1
