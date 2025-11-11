# Purpose: End-to-end tests for the BatchRunner pipeline.
# Verifies that running on image folders or single images correctly writes results to the database.

import pytest
from pathlib import Path
from sqlalchemy import text

from agri_baseline.src.batch_runner import BatchRunner
from agri_baseline.src.pipeline.db import get_engine


@pytest.fixture
def folder_with_images() -> Path:
    """
    Return a folder that contains a few test images.
    Adjust the path if your dataset sits elsewhere.
    """
    folder = Path("./data_balanced/PlantDoc/train/Bell_pepper leaf")
    assert folder.exists(), f"Images folder not found: {folder.resolve()}"
    return folder


def _count(conn, sql: str, params: dict | None = None) -> int:
    """
    Small helper: run a COUNT(*) query safely with SQLAlchemy 2.0.
    """
    return conn.execute(text(sql), params or {}).scalar() or 0


def test_run_batch_on_images_folder(folder_with_images: Path):
    """
    End-to-end: run the batch pipeline on a folder and verify DB writes happened.
    We compare counts before/after instead of relying on specific image_id values.
    """
    runner = BatchRunner()

    with get_engine().begin() as conn:
        before = _count(conn, "SELECT COUNT(1) FROM anomalies")

    runner.run_folder(folder_with_images)

    with get_engine().begin() as conn:
        after = _count(conn, "SELECT COUNT(1) FROM anomalies")

    assert after > before, "No detections were written to the database."


def test_process_single_image():
    """
    Process a single image and assert the DB anomalies count has increased.
    This avoids fragile assumptions on the exact image_id in the DB.
    """
    image_path = Path(
        "./data_balanced/PlantDoc/train/Bell_pepper leaf/0f3s5A.jpg"
    )
    assert image_path.exists(), f"Test image not found: {image_path.resolve()}"

    runner = BatchRunner()

    with get_engine().begin() as conn:
        before = _count(conn, "SELECT COUNT(1) FROM anomalies")

    runner.process_image(image_path)

    with get_engine().begin() as conn:
        after = _count(conn, "SELECT COUNT(1) FROM anomalies")

    assert after > before, "Single image was not processed correctly."
