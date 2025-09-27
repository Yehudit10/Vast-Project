import pytest
from types import SimpleNamespace
from core import db_io_pg

# ----------------------- Fakes / Helpers -----------------------

class FakeCursor:
    def __init__(self):
        self.executed = []
        self._fetchone = None 
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None):
        self.executed.append((sql, params))
    def fetchone(self):
        return self._fetchone
    def set_fetchone(self, value):
        self._fetchone = value

class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0
    def cursor(self): return self._cursor
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1

class FakeJson:
    def __init__(self, obj): self.obj = obj
    
    @property
    def dumps(self):
        import json
        return json.dumps(self.obj)
    
    @property
    def adapted(self):
        return self.obj


def make_fake_psycopg2(fake_conn):
    fake_extras = SimpleNamespace(Json=FakeJson)
    class _FakePsycopg2:
        extras = fake_extras
        def connect(self, dsn):
            return fake_conn
    return _FakePsycopg2()

# ----------------------- Fixtures -----------------------

@pytest.fixture
def cur():
    return FakeCursor()

@pytest.fixture
def conn(cur):
    return FakeConnection(cur)

@pytest.fixture
def psycopg2_fake(conn, monkeypatch):
    fake = make_fake_psycopg2(conn)
    monkeypatch.setattr(db_io_pg, "psycopg2", fake)
    return fake



# class FakeCursor:
#     def __init__(self, script=None):
#         self.executed = []
#         self.script = script or {}
#         self._fetchone = None
#     def __enter__(self): return self
#     def __exit__(self, exc_type, exc, tb): return False
#     def execute(self, sql, params=None):
#         self.executed.append((sql, params))
#         for pattern, action in self.script.items():
#             if re.search(pattern, str(sql), re.IGNORECASE):
#                 if isinstance(action, Exception): raise action
#                 if callable(action): action(sql, params)
#     def fetchone(self): return self._fetchone
#     def set_fetchone(self, value): self._fetchone = value
#     def close(self): pass


# class FakeConnection:
#     def __init__(self, cursor: FakeCursor):
#         self._cursor = cursor
#         self.commits = 0
#         self.rollbacks = 0
#         self.closed = False
#     def cursor(self): return self._cursor
#     def commit(self): self.commits += 1
#     def rollback(self): self.rollbacks += 1
#     def close(self): self.closed = True




# @pytest.fixture
# def psycopg2_fake(conn, monkeypatch):
#     """Monkeypatch db_io_pg.psycopg2 with a controllable fake."""
#     class FakeJson:
#         def __init__(self, obj): self.obj = obj
#     fake_extras = SimpleNamespace(Json=FakeJson)
#     class _FakePsycopg2:
#         extras = fake_extras
#         def connect(self, dsn): return conn
#     monkeypatch.setattr(db_io_pg, "psycopg2", _FakePsycopg2())
#     return _FakePsycopg2()
