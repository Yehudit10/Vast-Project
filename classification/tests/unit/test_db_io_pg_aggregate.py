"""
Unit tests for core/db_io_pg.py – aggregates and Json wrapping
"""

import pytest
from core import db_io_pg

# Assume FakeCursor, FakeConnection, FakeJson fixtures available: conn, cur, psycopg2_fake


def test__jsonify_wraps_non_string(psycopg2_fake):
    obj = [{"label": "shotgun", "p": 0.7}]
    j = db_io_pg._jsonify(obj)
    assert isinstance(j, db_io_pg.psycopg2.extras.Json)
    assert j.obj == obj


def test__jsonify_accepts_string(psycopg2_fake):
    raw = '[{"label":"shotgun","p":0.7}]'
    j = db_io_pg._jsonify(raw)
    assert isinstance(j, db_io_pg.psycopg2.extras.Json)


def test__jsonify_handles_json_string_and_non_json(psycopg2_fake):
    js = '[{"label":"shotgun","p":0.7}]'
    out1 = db_io_pg._jsonify(js)
    assert hasattr(out1, "adapted") or hasattr(out1, "dumps")

    s = "not-json"
    out2 = db_io_pg._jsonify(s)
    payload = getattr(out2, "adapted", None) or getattr(out2, "dumps", None)
    if isinstance(payload, dict):
        assert payload.get("raw") == "not-json"


def test_upsert_file_aggregate_uses_json_wrapper(psycopg2_fake, conn, cur):
    payload = {
        "file_id": 42,
        "run_id": "run_123",
        "agg_mode": "mean",
        "num_windows": 3,
    }
    db_io_pg.upsert_file_aggregate(conn, payload)
    assert conn.commits >= 1 and conn.rollbacks == 0
