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
from classification.core.db_utils import ensure_run, open_db, resolve_file_id
from classification.core.db_io_pg import finish_run, upsert_file_aggregate

app = FastAPI(title="Audio Classifier API", version="2.0.0")

# --- Globals (singletons) ---
PANN_MODEL: Optional[AudioTagging] = None
SK_PIPELINE = None 
DB_CONN = None
DB_RUN_ID = os.getenv("DB_RUN_ID", "api-default")
DB_SCHEMA = os.getenv("DB_SCHEMA", "agcloud_audio")

CHECKPOINT_PATH = os.getenv(
    "CHECKPOINT",
    "/app/classification/models/panns_data/Cnn14_mAP=0.431.pth"
)
HEAD_PATH = os.getenv(
    "HEAD",
    "/app/classification/models/head/head_cnn14_rf.joblib"  # adapt if different
)

class ClassifyIn(BaseModel):
    s3_bucket: str
    s3_key: str
    return_probs: bool = True

class ClassifyOut(BaseModel):
    label: str
    probs: Dict[str, float]


@app.on_event("startup")
def load_models_on_startup() -> None:
    """
    Load heavy models once and perform a short warm-up to avoid cold-start.
    Also open DB connection and ensure run row exists.    """
    global PANN_MODEL, SK_PIPELINE, DB_CONN
    logger = logging.getLogger("uvicorn.error")

    logger.info("Loading models into memory...")
    PANN_MODEL = AudioTagging(checkpoint_path=CHECKPOINT_PATH)
    SK_PIPELINE = None
    try:
        if os.path.exists(HEAD_PATH):
            SK_PIPELINE = joblib.load(HEAD_PATH)
            logger.info("✅ SK pipeline loaded from HEAD.")
        else:
            logger.warning(f"HEAD pipeline not found at {HEAD_PATH}; using built-in head.")
    except Exception as e:
        logger.warning(f"HEAD pipeline load failed ({e}); using built-in head.")

    # 3) Warm-up forward pass with 1 second of silence
    dummy = np.zeros((1, SAMPLE_RATE * 10), dtype=np.float32)  # add batch dim
    try:
        _ = PANN_MODEL.inference(dummy)
        logger.info("✅ PANN model warm-up complete.")
    except Exception as e:
        logger.warning(f"PANN warm-up skipped ({e})")
    
    # DB connect + ensure run
    try:
        DB_CONN = open_db()
        ensure_run(DB_CONN, DB_RUN_ID)
        logger.info(f"✅ DB connected; run '{DB_RUN_ID}' ensured in schema '{DB_SCHEMA}'.")
    except Exception as e:
        logger.error(f"DB init failed: {e}")
        raise
    
    logger.info("✅ All models loaded and ready.")

@app.on_event("shutdown")
def close_db_on_shutdown() -> None:
    """
    Cleanly close the global DB connection on shutdown.
    """
    global DB_CONN
    try: 
        if DB_CONN is not None:
            try:
                finish_run(DB_CONN, DB_RUN_ID)
            except Exception:
                pass
            DB_CONN.close()
    except Exception:
        pass
    finally:
        DB_CONN = None
        
# dedicated API perf logger
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
    - DB upsert into agcloud_audio.file_aggregates
    """
    start = time.perf_counter()
    status_code = 200
    try:
        # 1) Require the file to already exist in public.files → else 404
        try:
            file_id = resolve_file_id(DB_CONN, bucket=body.s3_bucket, object_key=body.s3_key)
        except ValueError as e:
            # file not found in public.files → return 404 (do NOT create)
            raise HTTPException(status_code=404, detail=str(e))

        # 2) Run classification
        result = cls_script.run_classification_job(
            s3_bucket=body.s3_bucket,
            s3_key=body.s3_key,
            pann_model=PANN_MODEL,
            sk_pipeline=SK_PIPELINE
        )

        # 3) Upsert aggregate to DB (JSONB)
        upsert_file_aggregate(DB_CONN, {
            "run_id": DB_RUN_ID,
            "file_id": file_id,
            "head_probs_json": result.get("probs", {}),
            "head_pred_label": result.get("label"),
            "head_pred_prob": result.get("pred_prob"),
            "head_unknown_threshold": result.get("unknown_threshold"),
            "head_is_another": result.get("is_another"),
            "num_windows": result.get("num_windows"),
            "agg_mode": result.get("agg_mode"),
            "processing_ms": result.get("processing_ms"),
        })

        # 4) Build API response
        out = {"label": result.get("label", ""), "probs": result.get("probs", {})}
        if not body.return_probs:
            out["probs"] = {}
        return ClassifyOut(**out)

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
