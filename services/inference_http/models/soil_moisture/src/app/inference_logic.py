"""
Shared inference logic that can be used by both the API and adapters.
"""
import logging
import time
import datetime as dt
from typing import Dict, Any, Tuple, Optional
from PIL import Image

logger = logging.getLogger(__name__)


class SoilMoistureInferenceLogic:
    """
    Encapsulates the inference logic for soil moisture detection.
    This can be used by both the FastAPI service and the Flink adapter.
    """
    
    def __init__(self, settings, db, inferencer, producer=None):
        self.settings = settings
        self.db = db
        self.inferencer = inferencer
        self.producer = producer
    
    def extract_device_id(self, filename: str) -> str:
        """
        Extract device ID from filename in the format device_ts
        (For example dev-f_20251106T1030.jpg)
        """
        import os
        base = os.path.basename(filename)
        device_id = base.split("_")[0]
        if not device_id:
            raise ValueError(f"Invalid filename format: {filename}")
        return device_id
    
    def build_idem_key(self, device_id: str, ts_unix: float) -> str:
        """Build idempotency key"""
        bucket = self.inferencer.decision_window_bucket(ts_unix)
        return f"{device_id}:{int(bucket)}"
    
    def publish_and_persist(
        self,
        device_id: str,
        decision: str,
        duration_min: int,
        confidence: float,
        dry_ratio: float,
        patch_count: int,
        idem: str,
        ts_iso: str
    ) -> bool:
        """
        Publish to Kafka and persist to database.
        Returns True if saved successfully, False if duplicate.
        """
        import json
        import os
        
        payload = {
            "device_id": device_id,
            "command": decision if decision in ("run", "stop") else "noop",
            "reason": "soil_dry",
            "duration_min": duration_min if decision == "run" else None,
            "confidence": confidence,
            "ts": ts_iso,
            "idempotency_key": idem
        }
        
        saved = self.db.log_event(
            device_id, ts_iso, dry_ratio, payload["command"],
            confidence, patch_count, idem,
            extra={"dry_ratio": dry_ratio}
        )
        
        if not saved:
            logger.info(json.dumps({
                "msg": "duplicate_idempotency",
                "device_id": device_id,
                "idem": idem
            }))
            return False
        
        # Schedule update
        schedule_update = os.getenv('SCHEDULE_UPDATE', '1') == '1'
        if schedule_update and decision == 'run':
            try:
                self.db.upsert_schedule(
                    device_id, ts_iso, duration_min,
                    updated_by='soil_api',
                    update_reason='soil_dry'
                )
            except Exception as e:
                logger.warning('schedule update failed: %s', e)
        
        # Publish to Kafka
        if self.producer:
            self.producer.publish(payload)
        else:
            logger.warning(
                "Kafka producer unavailable; skipping publish. payload=%s",
                payload
            )
        
        return True
    
    def infer_from_image(
        self,
        img: Image.Image,
        device_id: str,
        ts_unix: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Run inference on an image and return results.
        
        Args:
            img: PIL Image object
            device_id: Device identifier
            ts_unix: Unix timestamp (optional, defaults to current time)
        
        Returns:
            Dictionary with inference results including:
            - device_id
            - dry_ratio
            - decision
            - confidence
            - patch_count
            - duration_min
            - ts
            - idempotency_key
            - latency_ms
        """
        if ts_unix is None:
            ts_unix = time.time()
        
        start_time = time.time()
        ts_iso = dt.datetime.utcfromtimestamp(ts_unix).isoformat() + "Z"
        
        # Run inference
        result, debug = self.inferencer.infer_image(img, device_id)
        
        # Build idempotency key
        idem = self.build_idem_key(device_id, ts_unix)
        
        # Publish and persist
        saved = self.publish_and_persist(
            device_id=device_id,
            decision=result["decision"],
            duration_min=result["duration_min"],
            confidence=result["confidence"],
            dry_ratio=result["dry_ratio"],
            patch_count=result["patch_count"],
            idem=idem,
            ts_iso=ts_iso
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return {
            "device_id": device_id,
            "dry_ratio": result["dry_ratio"],
            "decision": result["decision"],
            "confidence": result["confidence"],
            "patch_count": result["patch_count"],
            "duration_min": result.get("duration_min", 0),
            "ts": ts_iso,
            "idempotency_key": idem,
            "latency_ms": latency_ms,
            "saved": saved,
            "debug": debug
        }