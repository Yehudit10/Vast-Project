
import os, time
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from minio import Minio
from model_registry import get_model_runner

TEAM = os.getenv("TEAM")
if not TEAM:
    raise RuntimeError("Missing TEAM environment variable – please set TEAM=<team_name>")

MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "minio-hot:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_SECURE     = os.getenv("MINIO_SECURE", "0") == "1"

app = FastAPI(title="Fruit Inference HTTP")

class InferRequest(BaseModel):
    # Accept only bucket+key; any other fields are rejected (422)
    model_config = ConfigDict(extra="forbid")
    bucket: str
    key: str


@app.on_event("startup")
def _startup():
    app.state.mc = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )
    # The runner already knows how to read image_uri from S3
    app.state.runner = get_model_runner(TEAM)

@app.get("/healthz")
def healthz():
    return {"ok": True, "team": TEAM}

@app.post("/infer_json")
def infer_json(
    req: InferRequest,
    idem_key: str | None = Header(default=None, alias="Idempotency-Key"),
    corr_id: str | None = Header(default=None, alias="X-Correlation-ID"),
):
    started = time.perf_counter()

    try:
        runner = app.state.runner

        # Always build the image URI from bucket and key
        s3_uri = f"s3://{req.bucket}/{req.key}"

        # Try to read the image bytes from MinIO
        obj = app.state.mc.get_object(req.bucket, req.key)
        try:
            image_bytes = obj.read()
        finally:
            obj.close()
            obj.release_conn()

        # Attempt to run the model with bytes input first
        # Attempt to run the model with bytes input first
        try:
            result = runner.run(image_bytes, extra={"bucket": req.bucket, "key": req.key})
        except TypeError:
            # If the function does not accept bytes, try with URI instead
            result = runner.run(s3_uri, extra={"bucket": req.bucket, "key": req.key})


        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": True,
            "team": TEAM,
            "result": result,
            "image_uri": s3_uri,
            "latency_ms": latency_ms,
            "idempotency_key": idem_key,
            "correlation_id": corr_id,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"inference failed: {e}")
