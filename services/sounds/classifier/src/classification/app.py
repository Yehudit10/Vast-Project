import logging
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
import os
import numpy as np
import joblib

from panns_inference import AudioTagging
from classification.core.model_io import SAMPLE_RATE
from classification.scripts import classify as cls_script

app = FastAPI(title="Audio Classifier API", version="2.0.0")

# --- Globals (singletons) ---
PANN_MODEL: Optional[AudioTagging] = None
SK_PIPELINE = None  # type: ignore

CHECKPOINT_PATH = os.getenv(
    "CHECKPOINT",
    "/app/classification/models/panns_data/Cnn14_mAP=0.431.pth"
)
SK_PIPELINE_PATH = os.getenv(
    "SK_PIPELINE_PATH",
    "/app/classification/models/head/head_cnn14_rf.joblib"  # adapt if different
)

class ClassifyIn(BaseModel):
    s3_bucket: str
    s3_key: str

class ClassifyOut(BaseModel):
    label: str
    probs: Dict[str, float]


@app.on_event("startup")
def load_models_on_startup() -> None:
    """
    Load heavy models once and perform a short warm-up to avoid cold-start
    on the first request.
    """
    global PANN_MODEL, SK_PIPELINE
    logger = logging.getLogger("uvicorn.error")

    logger.info("Loading models into memory...")
    # Initialize models
    PANN_MODEL = AudioTagging(checkpoint_path=CHECKPOINT_PATH)
    SK_PIPELINE = None
    try:
        if os.path.exists(SK_PIPELINE_PATH):
            SK_PIPELINE = joblib.load(SK_PIPELINE_PATH)
            logger.info("✅ SK pipeline loaded.")
        else:
            logger.warning(f"SK pipeline not found at {SK_PIPELINE_PATH}; using built-in head.")
    except Exception as e:
        logger.warning(f"SK pipeline load failed ({e}); using built-in head.")

    # 3) Warm-up forward pass with 1 second of silence
    dummy = np.zeros((1, SAMPLE_RATE * 10), dtype=np.float32)  # add batch dim
    try:
        _ = PANN_MODEL.inference(dummy)
        logger.info("✅ PANN model warm-up complete.")
    except Exception as e:
        logger.warning(f"PANN warm-up skipped ({e})")
        
    logger.info("✅ All models loaded and ready.")

# create a dedicated API perf logger
api_logger = logging.getLogger("audio_cls.api")
api_logger.setLevel(logging.INFO)
if not api_logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] [API] %(message)s", "%Y-%m-%d %H:%M:%S"))
    api_logger.addHandler(h)

@app.post("/classify", response_model=ClassifyOut)
def classify(body: ClassifyIn):
    """
    Run the full classification pipeline:
    - Download from MinIO (s3_bucket + s3_key)
    - Model inference with open-set threshold
    - Optional DB write
    - Optional Kafka alert (for known labels)
    """
    start = time.perf_counter()
    status_code = 200
    try:
        result = cls_script.run_classification_job(
            s3_bucket=body.s3_bucket,
            s3_key=body.s3_key,
            pann_model=PANN_MODEL,
            sk_pipeline=SK_PIPELINE 
        )
        return ClassifyOut(label=result["label"], probs=result["probs"])
    except HTTPException as e:
        status_code = e.status_code
        raise  
    except Exception as e:
        status_code = 500
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        api_logger.info(
            f"path=/classify bucket={body.s3_bucket} key={body.s3_key} "
            f"latency_ms={elapsed_ms:.2f} status={status_code}"
        )

@app.get("/health")
def health():
    return {
        "ok": True,
        "pann_loaded": PANN_MODEL is not None,
        "sk_pipeline_loaded": SK_PIPELINE is not None
    }


@app.middleware("http")
async def timing_middleware(request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # log only interesting routes (keep or adjust as you like)
    if request.url.path in ("/classify", "/health"):
        api_logger.info(f"path={request.url.path} status={response.status_code} latency_ms={elapsed_ms:.2f}")

    return response
