#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MegaDetector gRPC microservice — using the official Microsoft MDv5A model.

✅ Prometheus metrics:
   - Inference requests, errors, latency, model load time
   - System CPU, process CPU/memory, GPU usage (from monitoring.py)
"""

from __future__ import annotations
import io, os, time, grpc
from concurrent import futures
import numpy as np
from PIL import Image

# ─────────────────────────────────────────────
# MegaDetector import (official Microsoft model)
# ─────────────────────────────────────────────
from megadetector.detection import run_detector

# ─────────────────────────────────────────────
# Proto imports
# ─────────────────────────────────────────────
from agguard.proto import mega_detector_pb2 as pb2
from agguard.proto import mega_detector_pb2_grpc as pb2_grpc

# ─────────────────────────────────────────────
# Prometheus metrics (using your monitoring.py)
# ─────────────────────────────────────────────
from agguard.metrics.monitoring import (
    start_metrics_server,
    INFER_REQUESTS,
    INFER_ERRORS,
    INFER_LATENCY,
    MODEL_LOAD_SEC,
)


# ─────────────────────────────────────────────
# MegaDetector wrapper
# ─────────────────────────────────────────────
class SimpleMegaDetector:
    """Wrapper around official MegaDetector (v5A or v6A)."""

    CATEGORY_MAP = {"1": "animal", "2": "person", "3": "vehicle"}

    def __init__(self, model_name: str = "MDV5A", conf: float = 0.2):
        print(f"[MegaDetector] 🔹 Loading {model_name} ...")
        t0 = time.time()

        # Load model (downloads automatically if needed)
        self.model = run_detector.load_detector(model_name)
        self.conf = conf

        load_time = time.time() - t0
        MODEL_LOAD_SEC.labels(service="megadetector").set(load_time)
        print(f"[MegaDetector] ✅ Model loaded in {load_time:.1f}s")

    def detect(self, img: Image.Image) -> list[dict]:
        """Run detection on a PIL image."""
        image_np = np.array(img)
        result = self.model.generate_detections_one_image(image_np)
        detections = []

        for d in result.get("detections", []):
            if d.get("conf", 0) < self.conf:
                continue
            bbox = d["bbox"]  # normalized [x, y, w, h]
            detections.append({
                "category": self.CATEGORY_MAP.get(str(d["category"]), str(d["category"])),
                "conf": float(d["conf"]),
                "bbox": bbox
            })
        return detections


# ─────────────────────────────────────────────
# gRPC Servicer
# ─────────────────────────────────────────────
class MegaDetectorServicer(pb2_grpc.MegaDetectorServicer):
    """gRPC servicer for MegaDetector."""

    def __init__(self):
        model_name = os.getenv("MODEL_NAME", "MDV5A")
        conf_thresh = float(os.getenv("CONF_THRESH", "0.2"))
        self.detector = SimpleMegaDetector(model_name=model_name, conf=conf_thresh)

    def Detect(self, request, context):
        INFER_REQUESTS.labels(service="megadetector").inc()
        t0 = time.time()

        # Load image
        try:
            if request.image_bytes:
                img = Image.open(io.BytesIO(request.image_bytes)).convert("RGB")
            elif request.image_path:
                img = Image.open(request.image_path).convert("RGB")
            else:
                raise ValueError("No image provided")
        except Exception as e:
            INFER_ERRORS.labels(service="megadetector").inc()
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(f"Failed to load image: {e}")
            return pb2.DetectionResponse()

        # Run inference
        try:
            detections_raw = self.detector.detect(img)
        except Exception as e:
            INFER_ERRORS.labels(service="megadetector").inc()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Inference failed: {e}")
            return pb2.DetectionResponse()

        dt = time.time() - t0
        INFER_LATENCY.labels(service="megadetector").observe(dt)

        # Convert normalized → absolute coordinates
        w, h = img.size
        detections = []
        for det in detections_raw:
            x, y, bw, bh = det["bbox"]
            detections.append(
                pb2.Detection(
                    cls=det["category"],
                    conf=det["conf"],
                    x1=x * w, y1=y * h,
                    x2=(x + bw) * w, y2=(y + bh) * h,
                )
            )

        print(f"[MegaDetector] → {len(detections)} detections in {dt:.2f}s")
        return pb2.DetectionResponse(detections=detections, inference_time=dt)


# ─────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────
def serve():
    port = int(os.getenv("PORT", "50063"))
    metrics_port = int(os.getenv("METRICS_PORT", "8000"))

    # Start Prometheus metrics server (handles system/GPU collection)
    start_metrics_server()

    print(f"[MegaDetector] 📊 Metrics exposed on :{metrics_port}/metrics")

    # Start gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pb2_grpc.add_MegaDetectorServicer_to_server(MegaDetectorServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    print(f"[MegaDetector] 🚀 gRPC server running on port {port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()

