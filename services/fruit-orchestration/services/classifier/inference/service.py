import os
import io
import json
import time
from typing import Tuple

import torch
import torch.nn.functional as F
from PIL import Image

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from dotenv import load_dotenv
load_dotenv()

# --- מדדים ---
REQS = Counter("inference_requests_total", "Total inference requests")
ERRS = Counter("inference_errors_total", "Total inference errors")
LATENCY = Histogram("inference_latency_seconds", "Inference latency per image (seconds)")
LOADED = Gauge("model_loaded", "Model loaded (1=yes)")


from inference.utils_infer import build_infer_transforms, load_model
from metrics_db.db import insert_inference_log

app = FastAPI()

MODEL = None
LABELS = None
TFMS = None
CFG = None  

def _load_labels(labels_path: str):
    with open(labels_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    idx_to_class = {int(v): k for k, v in d.items()}
    return d, idx_to_class

def preprocess_image(file_bytes: bytes) -> torch.Tensor:
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    x = TFMS(img)              # [C,H,W]
    x = x.unsqueeze(0)         # [1,C,H,W]
    return x

def run_inference(model: torch.nn.Module, x: torch.Tensor, idx_to_class: dict) -> Tuple[str, float]:
    model.eval()
    with torch.no_grad():
        logits = model(x)
        probs = F.softmax(logits, dim=1)
        score, pred = probs.max(dim=1)  # [1]
        cls_idx = int(pred.item())
        cls_name = idx_to_class[cls_idx]
        return cls_name, float(score.item())

@app.on_event("startup")
def on_startup():
    """
    Load config, model, labels, and transforms once at startup.
    Supports load_model(...) returning either:
      - model
      - (model, labels_map) where labels_map is {class_name: idx} or {idx: class_name}
    """
    global MODEL, LABELS, TFMS, CFG

    weights_path = os.environ["WEIGHTS_PATH"]
    labels_path = os.environ["LABELS_PATH"]
    cfg_path = os.environ["CFG_PATH"]

    import yaml
    with open(cfg_path, "r", encoding="utf-8") as f:
        CFG = yaml.safe_load(f)

    # --- load model (support both signatures) ---
    res = load_model(weights_path, labels_path, backbone=CFG.get("backbone", "mobilenet_v3_small"))
    if isinstance(res, tuple):
        MODEL, labels_map = res
    else:
        MODEL = res
        # fallback: load labels_map from file
        with open(labels_path, "r", encoding="utf-8") as lf:
            labels_map = json.load(lf)

    # labels_map can be {class_name: idx} OR {idx: class_name}.
    # Normalize to idx_to_class: {int(idx): class_name}
    if all(isinstance(k, str) for k in labels_map.keys()):
        # assume {class_name: idx}
        idx_to_class = {int(v): str(k) for k, v in labels_map.items()}
    else:
        # assume {idx: class_name}
        idx_to_class = {int(k): str(v) for k, v in labels_map.items()}

    LABELS = labels_map
    app.state.idx_to_class = idx_to_class

    # --- transforms ---
    TFMS = build_infer_transforms(image_size=CFG.get("image_size", 224))

    # ready
    LOADED.set(1)
    print("Startup OK | model loaded:", type(MODEL).__name__,
          "| classes:", len(app.state.idx_to_class))


@app.post("/infer")
async def infer(file: UploadFile = File(...)):
    start = time.time()
    try:
        raw = await file.read()
        x = preprocess_image(raw)
        pred, score = run_inference(MODEL, x, app.state.idx_to_class)
        REQS.inc()
        latency_ms = (time.time() - start) * 1000.0
        LATENCY.observe(latency_ms / 1000.0)

        try:
            insert_inference_log(
                model_backbone=CFG.get("backbone", "mobilenet_v3_small"),
                image_size=CFG.get("image_size", 224),
                fruit_type=str(pred),
                score=float(score),
                latency_ms=float(latency_ms),
                client_ip="127.0.0.1",
                error=None,
            )
        except Exception as db_e:
            print(f"[WARN] DB insert failed: {db_e}")

        return {"fruit_type": pred, "score": score, "latency_ms": round(latency_ms, 2)}

    except Exception as e:
        ERRS.inc()
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
