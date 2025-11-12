"""
FastAPI service for soil moisture inference.
Delegates business logic to inference_logic.py
"""
import base64
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from .config import Settings, load_zones
from .schemas import InferRequest, InferResponse
from .inference import Inferencer
from .kafka_producer import ControlProducer
from .db import DB
from .metrics import METRICS
from .utils import load_image_from_b64
from .inference_logic import SoilMoistureInferenceLogic

logging.basicConfig(level=logging.DEBUG, format='%(message)s')
logger = logging.getLogger("soil_api")

# Initialize components
settings = Settings()
zones_cfg = load_zones(settings.zones_file)
db = DB(settings.pg_dsn)
inferencer = Inferencer(settings, db)

# Initialize Kafka producer
producer = None
try:
    from kafka import KafkaProducer
    producer = ControlProducer(
        settings.kafka_brokers,
        settings.kafka_topic,
        settings.kafka_dlt
    )
except Exception as e:
    import traceback
    logger.warning("Kafka init failed: %s\n%s", e, traceback.format_exc())

# Initialize shared inference logic
inference_logic = SoilMoistureInferenceLogic(
    settings=settings,
    db=db,
    inferencer=inferencer,
    producer=producer
)

app = FastAPI(title="Soil Moisture DL API", version="1.0.0")


@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"


@app.get("/ready", response_class=PlainTextResponse)
def ready():
    if not db.init_ok():
        raise HTTPException(status_code=503, detail="DB not ready")
    return "ready"


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/infer", response_model=InferResponse)
async def infer(image: UploadFile = File(None), body: InferRequest | None = None):
    """
    Run inference on a soil moisture image.
    Accepts either multipart form data (file upload) or JSON with base64 image.
    """
    # Parse input
    if body is not None:
        img = load_image_from_b64(body.image_b64)
        device_id = inference_logic.extract_device_id(body.filename)
    else:
        if image is None:
            raise HTTPException(
                status_code=400,
                detail="Provide multipart (file) or JSON (image_b64)"
            )
        filename = image.filename
        device_id = inference_logic.extract_device_id(filename)
        content = await image.read()
        img = load_image_from_b64(base64.b64encode(content).decode("utf-8"))
    
    # Run inference using shared logic
    result = inference_logic.infer_from_image(img, device_id)
    
    # Return response
    return InferResponse(
        device_id=result["device_id"],
        dry_ratio=result["dry_ratio"],
        decision=result["decision"],
        confidence=result["confidence"],
        patch_count=result["patch_count"],
        ts=result["ts"],
        idempotency_key=result["idempotency_key"]
    )