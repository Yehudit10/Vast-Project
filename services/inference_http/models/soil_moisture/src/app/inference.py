from typing import Dict, Any, Tuple
from PIL import Image
import numpy as np
import os, time, logging
from .config import Settings
from .utils import normalize_lighting, tile_image, preprocess_onnx
from .metrics import METRICS
from .onnx_model import ONNXMoistureModel
from .db import DB

logger = logging.getLogger("soil_api")

DRY_LABEL = "dry"

class Inferencer:
    def __init__(self, settings: Settings, db: DB,
                 model_path: str = "artifacts/model.onnx",
                 label_map_path: str = "artifacts/label_mapping.json"):
        self.settings = settings
        self.db = db
        self.model = ONNXMoistureModel(model_path, label_map_path)
        self.classes = [self.model.label_map[str(i)] for i in range(len(self.model.label_map))]

    def decision_window_bucket(self, ts: float) -> int:
        return int(ts // self.settings.decision_window_sec) * self.settings.decision_window_sec

    def infer_image(self, img: Image.Image, device_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:

        t0 = time.time()
        img_n = normalize_lighting(img)
        patches = tile_image(img_n, self.settings.patch_size, self.settings.patch_stride)

        dry_votes = 0
        probs = []

        logger.info("infer_image start device_id=%s patch_size=%d stride=%d total_patches=%d",device_id, self.settings.patch_size, self.settings.patch_stride, len(patches))

        try:
            dry_idx = self.classes.index(DRY_LABEL)
        except ValueError:
            logger.warning("DRY_LABEL '%s' not found in classes %s", DRY_LABEL, self.classes)
            dry_idx = None

        for idx, p in enumerate(patches):
            try:
                proba = self.model.predict_proba_patch(p)
            except Exception as e:
                logger.exception("model.predict_proba_patch failed for patch idx=%d: %s", idx, e)
                proba = np.zeros(len(self.classes), dtype=float)

            probs.append(proba)
            arg = int(proba.argmax()) if proba.size else -1
            arg_label = self.classes[arg] if (arg >= 0 and arg < len(self.classes)) else "unknown"
            maxp = float(proba.max()) if proba.size else 0.0
            logger.debug("patch idx=%d arg=%d label=%s maxp=%.4f", idx, arg, arg_label, maxp)

            if dry_idx is not None and arg == dry_idx:
                dry_votes += 1

        mean_confidence = float(np.mean([max(x) for x in probs])) if probs else 0.0

        patch_count = len(patches)
        dry_ratio = dry_votes / max(1, patch_count)

        # Policy / hysteresis
        policy = self.db.load_device_policy(device_id)
        prev_state    = policy.get("prev_state") or "stop"
        high          = policy.get("dry_ratio_high") or 0.35
        low           = policy.get("dry_ratio_low") or 0.25
        min_patches   = policy.get("min_patches") or 2
        duration_min  = policy.get("duration_min") or 10

        logger.info("decision inputs prev_state=%s dry_votes=%d patch_count=%d dry_ratio=%.4f high=%.4f low=%.4f min_patches=%d",
                    prev_state, dry_votes, patch_count, dry_ratio, high, low, min_patches)

        decision = "noop"
        if patch_count >= min_patches:
            if prev_state != "run" and dry_ratio >= high:
                decision = "run"
            elif prev_state != "stop" and dry_ratio <= low:
                decision = "stop"
            else:
                logger.debug("hysteresis conditions not met (prev_state=%s)", prev_state)
        else:
            logger.debug("not enough patches for decision: patch_count=%d min_patches=%d", patch_count, min_patches)

        new_state = decision if decision in ("run", "stop") else prev_state
        logger.info("decision result=%s updated_state=%s duration_min=%d confidence=%.4f",
                    decision, new_state, duration_min, mean_confidence)

        METRICS["inference_latency_ms"].observe((time.time() - t0) * 1000.0)

        result = {
            "dry_ratio": float(dry_ratio),
            "decision": decision,
            "confidence": float(mean_confidence),
            "patch_count": int(patch_count),
            "duration_min": duration_min
        }
        debug = {
            "probs_shape": (len(probs), len(probs[0]) if probs else 0)
        }
        if new_state != prev_state:
            self.db.update_prev_state(device_id, new_state)

        return result, debug
