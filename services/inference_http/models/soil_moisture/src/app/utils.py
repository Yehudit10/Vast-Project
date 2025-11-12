import base64, io
from PIL import Image, ImageOps
import numpy as np
from typing import List

def load_image_from_b64(b64: str) -> Image.Image:
    data = base64.b64decode(b64)
    return Image.open(io.BytesIO(data)).convert("RGB")

def normalize_lighting(img: Image.Image) -> Image.Image:
    r, g, b = img.split()
    r, g, b = ImageOps.equalize(r), ImageOps.equalize(g), ImageOps.equalize(b)
    return Image.merge("RGB", (r, g, b))

def tile_image(img: Image.Image, patch_size: int, stride: int) -> List[Image.Image]:
    w, h = img.size
    patches = []
    for y in range(0, h - patch_size + 1, stride):
        for x in range(0, w - patch_size + 1, stride):
            patches.append(img.crop((x, y, x + patch_size, y + patch_size)))
    if not patches:
        patches.append(img.resize((patch_size, patch_size)))
    return patches

def preprocess_onnx(pil_img: Image.Image, size: int = 224) -> np.ndarray:
    img = pil_img.resize((size, size))
    arr = np.asarray(img).astype("float32") / 255.0
    arr = arr.transpose(2,0,1)  # HWC -> CHW
    return arr[None, :, :, :]   # NCHW
