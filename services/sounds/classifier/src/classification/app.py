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
    "/app/classification/models/sk_pipeline.joblib"  # adapt if different
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

    # 1) Load PANNs model once
    PANN_MODEL = AudioTagging(
        checkpoint_path=CHECKPOINT_PATH,
        device="cpu"
    )

    # 2) Load sklearn pipeline (pin scikit-learn to the save-time version)
    if os.path.exists(SK_PIPELINE_PATH):
        SK_PIPELINE = joblib.load(SK_PIPELINE_PATH)

    # 3) Warm-up forward pass with 1 second of silence
    dummy = np.zeros((1, SAMPLE_RATE * 10), dtype=np.float32)  # add batch dim
    try:
        _ = PANN_MODEL.inference(dummy)
    except Exception as e:
        # Do not crash the app on warm-up; just log and continue
        import logging
        logging.getLogger("uvicorn.error").warning(f"PANN warm-up skipped: {e}")

@app.post("/classify", response_model=ClassifyOut)
def classify(body: ClassifyIn):
    """
    Run the full classification pipeline:
    - Download from MinIO (s3_bucket + s3_key)
    - Model inference with open-set threshold
    - Optional DB write
    - Optional Kafka alert (for known labels)
    """
    try:
        result = cls_script.run_classification_job(
            s3_bucket=body.s3_bucket,
            s3_key=body.s3_key,
            pann_model=PANN_MODEL,
            sk_pipeline=SK_PIPELINE 
        )
        return ClassifyOut(label=result["label"], probs=result["probs"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {
        "ok": True,
        "pann_loaded": PANN_MODEL is not None,
        "sk_pipeline_loaded": SK_PIPELINE is not None
    }