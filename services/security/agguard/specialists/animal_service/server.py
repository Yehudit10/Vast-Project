#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Animal Classifier microservice — reusing mask-classifier.proto.
Maps model class names (e.g., "american_black_bear", "sloth_bear")
to unified labels (e.g., "bear"). Unrecognized classes → "other".
Now includes Prometheus metrics and system monitoring.
"""

from __future__ import annotations
import io, os, time, grpc
from concurrent import futures
from PIL import Image
from ultralytics import YOLO
from agguard.proto import mask_classifier_pb2 as pb2
from agguard.proto import mask_classifier_pb2_grpc as pb2_grpc

# ─────────────────────────────────────────────
# Prometheus metrics import
# ─────────────────────────────────────────────
from agguard.metrics.monitoring import (
    start_metrics_server,
    INFER_REQUESTS, INFER_ERRORS, INFER_LATENCY, MODEL_LOAD_SEC
)


class AnimalClassifierServicer(pb2_grpc.ClassifierServiceServicer):
    def __init__(self):
        model_path = os.getenv("MODEL_PATH", "/app/weights/yolov8n-cls.pt")
        print(f"[AnimalClassifier] 🔹 Loading {model_path} ...")
        t0 = time.time()

        self.model = YOLO(model_path)
        load_time = time.time() - t0
        MODEL_LOAD_SEC.labels(service="animal_classifier").set(load_time)
        print(f"[AnimalClassifier] ✅ Model loaded in {load_time:.1f}s")

        # ─────────────────────────────────────────────
        # Class mapping
        # ─────────────────────────────────────────────
        self.label_map = {
            # Bears
            "american_black_bear": "bear",
            "sloth_bear": "bear",
            "brown_bear": "bear",
            "gibbon": "bear",
            "siamang": "bear",
            "velvet": "bear",
            "colobus": "bear",
            "indri": "bear",
            "howler_monkey": "bear",
            "capuchin":"bear",
            # Foxes
            "red_fox": "fox",
            "grey_fox": "fox",
            "kit_fox": "fox",
            "white_wolf": "fox",
            "kuvasz": "fox",
            "dugong": "fox",
            "arctic_fox": "fox",
            "fox_squirrel": "fox",
            "hog": "fox",
            "tusker": "fox",
            "mink": "fox",
            "jay": "fox",
            # Others
            "wild_boar": "boar",
            "wolf": "wolf",
            "deer": "deer",
            "rabbit": "rabbit",
        }
        self.intruding = set(self.label_map.values())

    def _predict(self, jpeg: bytes):
        img = Image.open(io.BytesIO(jpeg)).convert("RGB")
        res = self.model.predict(img, verbose=False)[0]
        idx = res.probs.top1
        conf = float(res.probs.top1conf.item())
        raw_label = res.names[idx].lower().strip()

        label = self.label_map.get(raw_label, "other")
        if label not in self.intruding:
            label = "other"

        print(f"[AnimalClassifier] raw={raw_label}, mapped={label}, conf={conf:.3f}")
        return label, conf

    def Classify(self, request, context):
        INFER_REQUESTS.labels(service="animal_classifier").inc()
        t0 = time.time()
        preds = []
        try:
            for crop in request.crops:
                try:
                    label, conf = self._predict(crop.jpeg)
                except Exception as e:
                    INFER_ERRORS.labels(service="animal_classifier").inc()
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details(f"Failed to classify crop: {e}")
                    return pb2.ClassifyResponse()
                preds.append(pb2.Prediction(
                    label=label,
                    confidence=conf,
                    x1=crop.x1, y1=crop.y1, x2=crop.x2, y2=crop.y2,
                ))
        except Exception as e:
            INFER_ERRORS.labels(service="animal_classifier").inc()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.ClassifyResponse()

        dt = time.time() - t0
        INFER_LATENCY.labels(service="animal_classifier").observe(dt)

        print(f"[AnimalClassifier] → {len(preds)} predictions in {dt:.2f}s")
        return pb2.ClassifyResponse(preds=preds)


def serve():
    port = int(os.getenv("PORT", "50064"))
    metrics_port = int(os.getenv("METRICS_PORT", "8008"))

    start_metrics_server()
    print(f"[AnimalClassifier] 📊 Metrics exposed on :{metrics_port}/metrics")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pb2_grpc.add_ClassifierServiceServicer_to_server(AnimalClassifierServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    print(f"[AnimalClassifier] 🚀 gRPC server running on port {port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
