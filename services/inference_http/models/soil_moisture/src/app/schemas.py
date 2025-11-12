from pydantic import BaseModel

class InferRequest(BaseModel):
    device_id: str
    image_b64: str  # base64-encoded RGB image

class InferResponse(BaseModel):
    device_id: str
    dry_ratio: float
    decision: str
    confidence: float
    patch_count: int
    ts: str
    idempotency_key: str
