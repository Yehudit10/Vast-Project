"""
Unit tests for core/db_io_pg.py – connection and schema management
"""

import re
import pytest
from types import SimpleNamespace
from core import db_io_pg


# ----------------------- open_db -----------------------

def test_open_db_missing_url_raises(psycopg2_fake):
    with pytest.raises(ValueError):
        db_io_pg.open_db(db_url="", schema="audio_cls")


@pytest.mark.parametrize("schema", ["bad-dash", "with space", "evil;drop", "💥", "a.b", "a*"])
def test_open_db_invalid_schema_raises(psycopg2_fake, schema):
    with pytest.raises(ValueError):
        db_io_pg.open_db(db_url="postgresql://user:pass@localhost/db", schema=schema)


def test_open_db_happy_path(psycopg2_fake, conn, cur):
    db = db_io_pg.open_db(
        db_url="postgresql://user:pass@localhost:5432/db",
        schema="audio_cls"
    )
    assert db is conn
    text = "\n".join(str(sql) for (sql, _params) in cur.executed)
    assert "audio_cls" in text
    assert conn.commits >= 1
    assert conn.rollbacks == 0


def test_open_db_rollback_on_exception(monkeypatch, conn, cur):
    """Force exception during schema setup to test rollback."""
    def bad_execute(sql, params=None): raise RuntimeError("boom")
    cur.execute = bad_execute
    monkeypatch.setattr(db_io_pg.psycopg2, "connect", lambda url: conn, raising=True)
    with pytest.raises(RuntimeError):
        db_io_pg.open_db("postgresql://u:p@h:5432/db", schema="audio_cls")
    assert conn.rollbacks >= 1


def test_open_db_rejects_invalid_schema_name():
    with pytest.raises(ValueError):
        db_io_pg.open_db(db_url="postgresql://u:p@h:5432/db", schema="not-valid!")
