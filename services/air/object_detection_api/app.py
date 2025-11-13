from fastapi import FastAPI, UploadFile, File, Query
from fastapi.responses import JSONResponse
from typing import Dict
from io import BytesIO
from PIL import Image
import numpy as np
import logging, os
from pathlib import Path

from model_wrapper import (
    ModelWrapper,
    mask_to_detections,
    merge_detections,
)

# -----------------------------------------------------------
# Logger setup
# -----------------------------------------------------------
logger = logging.getLogger("fusion_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -----------------------------------------------------------
# App initialization
# -----------------------------------------------------------
app = FastAPI(title="YOLO + Segmentation Fusion API", version="2.2")

WEIGHTS_PATH = os.getenv("WEIGHTS_PATH", "/app/object_detection_api.pt")
model = ModelWrapper(weights_path=WEIGHTS_PATH, conf=0.25, iou=0.45)

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


# -----------------------------------------------------------
# Utility: convert NumPy types to JSON serializable types
# -----------------------------------------------------------
def convert_numpy(obj):
    """Recursively convert NumPy data types to native Python types."""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (list, tuple)):
        return [convert_numpy(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_numpy(v) for k, v in obj.items()}
    else:
        return obj


# -----------------------------------------------------------
# Count detections by class
# -----------------------------------------------------------
def count_by_class(detections):
    counts = {}
    for _, name, _, *_ in detections:
        counts[name] = counts.get(name, 0) + 1
    return counts


# -----------------------------------------------------------
# Build readable summary text
# -----------------------------------------------------------
def build_summary(counts: Dict[str, int]) -> str:
    total = sum(counts.values())
    details = ", ".join([f"{v} {k}" for k, v in counts.items()])
    return f"Total: {total} detections — {details}"


# -----------------------------------------------------------
# Health check
# -----------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "weights": str(WEIGHTS_PATH)}


# -----------------------------------------------------------
# Inference route
# -----------------------------------------------------------
@app.post("/infer")
async def infer(
    image: UploadFile = File(...),
    mask: UploadFile = File(...),
    conf: float = Query(0.25, ge=0.0, le=1.0),
    iou: float = Query(0.45, ge=0.0, le=1.0),
):
    try:
        img_data = await image.read()
        mask_data = await mask.read()
        pil_image = Image.open(BytesIO(img_data)).convert("RGB")
        mask_image = Image.open(BytesIO(mask_data)).convert("RGB")

        logger.info(f"📸 Loaded image: {image.filename}, mask size: {mask_image.size}")

        model.conf = conf
        model.iou = iou
        yolo_dets = model.predict(pil_image)
        logger.info(f"🔹 YOLO detections: {len(yolo_dets)}")

        mask_dets = mask_to_detections(mask_image)
        logger.info(f"🔹 Mask detections: {len(mask_dets)}")

        final_dets = merge_detections(yolo_dets, mask_dets)
        logger.info(f"🔸 After merge: {len(final_dets)} total detections")

        counts = count_by_class(final_dets)
        summary_text = build_summary(counts)

        result = {
            "summary": summary_text,
            "counts_per_class": counts,
            "detections": [
                {
                    "class_id": d[0],
                    "class_name": d[1],
                    "confidence": d[2],
                    "bbox": [d[3], d[4], d[5], d[6]]
                }
                for d in final_dets
            ],
        }

        return JSONResponse(content=convert_numpy(result))

    except Exception as e:
        logger.exception(f"❌ Error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})