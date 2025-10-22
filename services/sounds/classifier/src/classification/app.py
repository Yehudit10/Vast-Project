from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict
from classification.scripts import classify as cls_script

app = FastAPI(title="Audio Classifier API", version="2.0.0")

class ClassifyIn(BaseModel):
    s3_bucket: str
    s3_key: str

class ClassifyOut(BaseModel):
    label: str
    probs: Dict[str, float]

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
        )
        return ClassifyOut(label=result["label"], probs=result["probs"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"ok": True}