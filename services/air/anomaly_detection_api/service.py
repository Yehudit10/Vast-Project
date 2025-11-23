from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from ultralytics import YOLO
from PIL import Image
import io, time
import os

# ===================================================
# Load YOLO model once
# ===================================================
MODEL_PATH = "models/anomaly_detection_api.pt"

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"❌ Model weights not found at: {MODEL_PATH}")

model = YOLO(MODEL_PATH)

app = FastAPI(title="Anomaly Detection API", version="1.0")


def run_inference(file: UploadFile):
    """Run YOLO inference in memory and return results."""
    image = Image.open(io.BytesIO(file.file.read()))
    return model.predict(image, conf=0.4, iou=0.25, save=False)


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    """Accepts an image, runs inference, and returns JSON with detections."""
    t0 = time.time()
    results = run_inference(file)

    if not results or len(results[0].boxes) == 0:
        return JSONResponse({
            "anomaly": False,
            "description": "No anomaly detected.",
            "inference_time_sec": round(time.time() - t0, 3)
        })

    h, w = results[0].orig_shape
    detections = []
    for box in results[0].boxes:
        cls = int(box.cls[0])
        detections.append({
            "label": model.names[cls],
            "confidence": round(float(box.conf[0]), 3),
            "bbox": [round(float(x), 1) for x in box.xyxy[0].tolist()],
            "center_xy": [round(float(x), 1) for x in box.xywh[0][:2].tolist()],
            "image_size": [w, h]
        })

    return JSONResponse({
        "anomaly": True,
        "detections": detections,
        "inference_time_sec": round(time.time() - t0, 3)
    })


@app.get("/health")
async def health():
    """Simple healthcheck endpoint."""
    return {"status": "ok", "model": MODEL_PATH}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("service:app", host="0.0.0.0", port=8010)
