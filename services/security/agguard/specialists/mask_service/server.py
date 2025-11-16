# agguard/specialists/mask_service/server.py
from __future__ import annotations
import os, logging, time
from concurrent import futures
from typing import List

import cv2
import numpy as np
import grpc

from agguard.proto import mask_classifier_pb2 as pb
from agguard.proto import mask_classifier_pb2_grpc as pbrpc

from agguard.specialists.mask_service.mask_classifier import FaceMaskClassifier, MaskPrediction

# ─────────────────────────────────────────────
# Prometheus metrics import
# ─────────────────────────────────────────────
from agguard.metrics.monitoring import (
    start_metrics_server,
    INFER_REQUESTS, INFER_ERRORS, INFER_LATENCY, MODEL_LOAD_SEC
)

log = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))


def _jpeg_to_rgb(j: bytes) -> np.ndarray:
    arr = np.frombuffer(j, dtype=np.uint8)
    img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError("Failed to decode JPEG")
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)


def _resize_square(rgb: np.ndarray, size: int) -> np.ndarray:
    return cv2.resize(rgb, (size, size), interpolation=cv2.INTER_LINEAR)


# ─────────────────────────────────────────────
# tolerate either service name in generated stubs
# ─────────────────────────────────────────────
ServicerBase = getattr(pbrpc, "ClassifierServiceServicer",
                       getattr(pbrpc, "ClassifierServicer", None))
if ServicerBase is None:
    raise ImportError("No Classifier{Service}Servicer in mask_classifier_pb2_grpc.py")

add_servicer = getattr(pbrpc, "add_ClassifierServiceServicer_to_server",
                       getattr(pbrpc, "add_ClassifierServicer_to_server", None))
if add_servicer is None:
    raise ImportError("No add_Classifier{Service}Servicer_to_server in mask_classifier_pb2_grpc.py")


class ClassifierService(ServicerBase):
    def __init__(self, model: FaceMaskClassifier):
        self.model = model

    def Classify(self, request: pb.ClassifyRequest, context) -> pb.ClassifyResponse:
        service_name = "mask_classifier"
        INFER_REQUESTS.labels(service=service_name).inc()
        t0 = time.time()

        crops_rgb: List[np.ndarray] = []
        boxes = []
        for c in request.crops:
            try:
                rgb = _jpeg_to_rgb(c.jpeg)
                rgb = _resize_square(rgb, self.model.imgsz)
                crops_rgb.append(rgb)
                boxes.append((c.x1, c.y1, c.x2, c.y2))
            except Exception as e:
                log.warning("Failed to decode crop: %s", e)

        preds: List[MaskPrediction] = []
        try:
            if crops_rgb:
                if self.model.backend == "torch":
                    preds = self.model._infer_torch(crops_rgb, boxes)
                else:
                    preds = self.model._infer_onnx(crops_rgb, boxes)
        except Exception as e:
            INFER_ERRORS.labels(service=service_name).inc()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb.ClassifyResponse()

        # Record latency metric
        dt = time.time() - t0
        INFER_LATENCY.labels(service=service_name).observe(dt)
        log.info("[MaskClassifier] → %d predictions in %.2fs", len(preds), dt)

        out = pb.ClassifyResponse()
        for p in preds:
            out.preds.add(
                x1=p.box[0], y1=p.box[1], x2=p.box[2], y2=p.box[3],
                label=p.label.lower(), confidence=float(p.confidence)
            )
        return out


def serve():
    backend = os.environ.get("BACKEND", "onnx").lower()
    model_path = os.environ.get("MODEL_PATH", "/app/weights/mask_yolov8.onnx")
    imgsz = int(os.environ.get("IMGSZ", "224"))
    device = os.environ.get("DEVICE", "cpu")
    classes = os.environ.get("CLASSES")
    class_names = [s.strip() for s in classes.split(",")] if classes else None

    log.info("[MaskClassifier] 🔹 Loading model: %s", model_path)
    t0 = time.time()
    model = FaceMaskClassifier(
        model_path=model_path, backend=backend, imgsz=imgsz, device=device, class_names=class_names
    )
    load_time = time.time() - t0
    MODEL_LOAD_SEC.labels(service="mask_classifier").set(load_time)
    log.info("[MaskClassifier] ✅ Model loaded in %.1fs", load_time)

    port = int(os.environ.get("PORT", "50061"))
    metrics_port = int(os.environ.get("METRICS_PORT", "8012"))

    # Start Prometheus metrics server
    start_metrics_server()
    log.info("[MaskClassifier] 📊 Prometheus metrics available at :%d/metrics", metrics_port)

    # Start gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    add_servicer(ClassifierService(model), server)
    server.add_insecure_port(f"[::]:{port}")
    log.info("[MaskClassifier] 🚀 gRPC server listening on :%d", port)
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()

