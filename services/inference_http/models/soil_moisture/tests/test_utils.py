import base64
import io
from PIL import Image
import numpy as np

from app.utils import (
    load_image_from_b64,
    normalize_lighting,
    tile_image,
    preprocess_onnx,
)


def make_rgb_image(w=8, h=6, color=(120, 100, 80)):
    return Image.new("RGB", (w, h), color=color)


def test_load_image_from_b64_roundtrip():
    img = make_rgb_image(5, 7, (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    out = load_image_from_b64(b64)
    assert out.mode == "RGB"
    assert out.size == (5, 7)


def test_normalize_lighting_basic_properties():
    img = make_rgb_image(10, 10, (50, 100, 150))
    out = normalize_lighting(img)
    assert out.mode == "RGB"
    assert out.size == img.size


def test_tile_image_regular_grid():
    img = make_rgb_image(5, 5, (0, 0, 0))
    patches = tile_image(img, patch_size=3, stride=2)
    # Positions: x in {0,2}, y in {0,2} => 4 patches
    assert len(patches) == 4
    assert all(p.size == (3, 3) for p in patches)


def test_tile_image_small_image_resizes_to_single_patch():
    img = make_rgb_image(2, 2, (0, 0, 0))
    patches = tile_image(img, patch_size=4, stride=4)
    assert len(patches) == 1
    assert patches[0].size == (4, 4)


def test_preprocess_onnx_output_shape_and_range():
    img = make_rgb_image(6, 6, (255, 128, 0))
    arr = preprocess_onnx(img, size=8)
    assert arr.shape == (1, 3, 8, 8)
    assert arr.dtype == np.float32
    assert np.isfinite(arr).all()
    assert arr.min() >= 0.0 and arr.max() <= 1.0

