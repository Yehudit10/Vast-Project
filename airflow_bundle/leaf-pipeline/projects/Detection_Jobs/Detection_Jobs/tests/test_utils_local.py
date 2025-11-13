# Purpose: Local unit tests for utility functions.
# Covers image loading, image ID extraction, and bounding box clamping logic.

from pathlib import Path
from PIL import Image
from agri_baseline.src.pipeline.utils import load_image, image_id_from_path, clamp_bbox

def _write_test_image(tmp_dir: Path, name: str = "test.jpg") -> Path:
    img = Image.new("RGB", (64, 48), (127, 200, 50))
    path = tmp_dir / name
    img.save(path, format="JPEG")
    return path

def test_load_image_local(tmp_path: Path):
    img_path = _write_test_image(tmp_path)
    img, w, h = load_image(str(img_path))
    assert img is not None
    assert (w, h) == (64, 48)

def test_image_id_from_path_no_fs(tmp_path: Path):
    fake_path = tmp_path / "nested" / "test.jpg"  # no file needed
    image_id = image_id_from_path(str(fake_path))
    assert isinstance(image_id, str) and image_id

def test_clamp_bbox_pure():
    x, y, w, h = clamp_bbox(10, 10, 250, 250, 224, 224)
    assert x >= 0 and y >= 0 and w <= 224 and h <= 224
