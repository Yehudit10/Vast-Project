# Purpose: Integration tests for the Validator module.
# Verifies event logging from findings and correctness of batch summary generation in the database.

import pytest
from sqlalchemy import text

from agri_baseline.src.validator.validator import Validator
from agri_baseline.src.validator.rules import Finding
from agri_baseline.src.pipeline.db import get_engine
from agri_baseline.src.pipeline import config
from agri_baseline.src.pipeline.db import get_engine

@pytest.fixture(autouse=True)
def _seed_anomalies_for_summary():
    """
    Ensure the DB has minimal data for batch_summary:
    - device 'device-1'
    - anomaly type id=1
    - mission id=1 with small polygon
    - two anomalies with same image_id and non-null geom
    Idempotent: safe to run before every test.
    """
    with get_engine().begin() as conn:
        conn.exec_driver_sql("""
        INSERT INTO devices(device_id, model, owner, active)
        VALUES ('device-1','sim','lab',true)
        ON CONFLICT (device_id) DO NOTHING;
        """)
        conn.exec_driver_sql("""
        INSERT INTO anomaly_types(anomaly_type_id, code, description)
        VALUES (1,'disease_spot','Leaf disease spot')
        ON CONFLICT (anomaly_type_id) DO NOTHING;
        """)
        conn.exec_driver_sql("""
        INSERT INTO missions(mission_id, start_time, area_geom)
        VALUES (1, now(), ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))',4326))
        ON CONFLICT (mission_id) DO NOTHING;
        """)
        conn.exec_driver_sql("""
        INSERT INTO anomalies(mission_id, device_id, ts, anomaly_type_id, severity, details, geom)
        VALUES
          (1, 'device-1', now(), 1, 0.6,
            '{"image_id":"seed_img_for_summary"}'::jsonb,
            ST_GeomFromText('POINT(0.50 0.50)',4326)),
          (1, 'device-1', now(), 1, 0.7,
            '{"image_id":"seed_img_for_summary"}'::jsonb,
            ST_GeomFromText('POINT(0.55 0.52)',4326))
        ON CONFLICT DO NOTHING;
        """)
    yield

@pytest.fixture
def dummy_finding() -> Finding:
    """
    Create a minimal Finding to simulate a validator output.
    Scope/value names should match your Validator implementation.
    """
    return Finding(
        scope="image",
        image_id="test_image",
        rule="bbox_oob",
        severity="warn",
        message="BBox out of bounds",
    )


def _count(conn, sql: str, params: dict | None = None) -> int:
    """
    Small helper: run a COUNT(*) query safely with SQLAlchemy 2.0.
    """
    return conn.execute(text(sql), params or {}).scalar() or 0


def test_validator_image_findings(dummy_finding: Finding):
    """
    Ensure validator writes a record into event_logs for the given finding.
    We assert a strictly increasing count for the message we inserted.
    """
    validator = Validator()

    with get_engine().begin() as conn:
        before = _count(
            conn,
            "SELECT COUNT(1) FROM event_logs WHERE message = :msg",
            {"msg": dummy_finding.message},
        )

    validator.image_findings([dummy_finding])

    with get_engine().begin() as conn:
        after = _count(
            conn,
            "SELECT COUNT(1) FROM event_logs WHERE message = :msg",
            {"msg": dummy_finding.message},
        )

    assert after > before, "Finding was not written to event_logs."


def test_batch_summary():
    """
    Run batch_summary and verify tile_stats is populated or remains populated.
    We allow idempotency (>=) but also require that there is some data (> 0).
    """
    validator = Validator()

    with get_engine().begin() as conn:
        print("DEBUG DB_URL:", config.DB_URL)
        print("DEBUG anomalies:", conn.exec_driver_sql("SELECT COUNT(*) FROM anomalies").scalar())
        print("DEBUG tile_stats:", conn.exec_driver_sql("SELECT COUNT(*) FROM tile_stats").scalar())
        before = _count(conn, "SELECT COUNT(1) FROM tile_stats")

    validator.batch_summary()

    with get_engine().begin() as conn:
        after = _count(conn, "SELECT COUNT(1) FROM tile_stats")

    assert after >= before, "tile_stats count unexpectedly decreased."
    assert after > 0, "No images found in tile_stats for batch summary."
