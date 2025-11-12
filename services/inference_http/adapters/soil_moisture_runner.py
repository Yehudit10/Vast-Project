
"""
Adapter for soil moisture inference in the generic HTTP inference flow.
Uses the shared inference logic from the soil-moisture service.
"""

import os
import base64
import logging
import sys
from typing import Any, Dict, Optional
from PIL import Image
from io import BytesIO
import numpy as np
import cv2
import time
import re

logger = logging.getLogger(__name__)


class SoilMoistureRunner:
    """
    Adapter that wraps the soil moisture inference logic.
    """
    
    def __init__(self, weights_path: Optional[str] = None, model_tag: Optional[str] = None):
        self.model_tag = model_tag
        self.weights_path = weights_path
        
        try:
            # Add models directory to path
            models_dir = os.path.join(os.path.dirname(__file__), '..', 'models')
            if models_dir not in sys.path:
                sys.path.insert(0, models_dir)
            
            # Import soil moisture components
            from soil_moisture.src.app.config import Settings, load_zones
            from soil_moisture.src.app.inference import Inferencer
            from soil_moisture.src.app.db import DB
            from soil_moisture.src.app.inference_logic import SoilMoistureInferenceLogic
            
            logger.info("Initializing SoilMoistureRunner...")
            
            # Initialize components
            self.settings = Settings()
            
            # Load zones config if available
            if hasattr(self.settings, 'zones_file') and self.settings.zones_file:
                if os.path.exists(self.settings.zones_file):
                    self.zones_cfg = load_zones(self.settings.zones_file)
                else:
                    logger.warning(f"zones_file not found: {self.settings.zones_file}")
                    self.zones_cfg = {}
            else:
                self.zones_cfg = {}
            
            self.db = DB(self.settings.pg_dsn)
            self.inferencer = Inferencer(self.settings, self.db)
            
            # Initialize Kafka producer (optional)
            producer = None
            try:
                from soil_moisture.src.app.kafka_producer import ControlProducer
                producer = ControlProducer(
                    self.settings.kafka_brokers,
                    self.settings.kafka_topic,
                    self.settings.kafka_dlt
                )
            except Exception as e:
                logger.warning(f"Kafka producer init failed: {e}")
            
            # Initialize shared inference logic
            self.inference_logic = SoilMoistureInferenceLogic(
                settings=self.settings,
                db=self.db,
                inferencer=self.inferencer,
                producer=producer
            )
            
            logger.info("SoilMoistureRunner initialized successfully!")
            
        except Exception as e:
            logger.error(f"Failed to initialize SoilMoistureRunner: {e}", exc_info=True)
            raise
   
    def run(self, image_bytes: Any, model_tag: Optional[str] = None, 
            extra: Optional[Dict] = None) -> Dict:
        """
        Run soil moisture inference using the shared inference logic.
        """
        start_time = time.time()

        try:
            bucket_in = extra.get("bucket") if extra else "imagery"
            key = extra.get("key") if extra else None
            if not key:
                return {"error": "missing key"}

            # --- Extract device_id from the key (pattern: path/to/image/dev-id_ts.jpg) ---
            def extract_device_id_from_key(key: str) -> str:
                filename = key.split("/")[-1]  # get "dev-id_ts.jpg"
                match = re.match(r"([^_]+)_", filename)  # capture part before "_"
                if match:
                    return match.group(1)
                return "unknown"

            # --- Decode image ---
            img_array = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img is None:
                return {"error": "failed to decode image from bytes"}

            # --- Determine device_id ---
            device_id = "unknown"
            if extra:
                if "device_id" in extra:
                    device_id = extra["device_id"]
                elif "filename" in extra:
                    device_id = self.inference_logic.extract_device_id(extra["filename"])
                elif "key" in extra:
                    device_id = extract_device_id_from_key(extra["key"])

            # --- Convert input to PIL Image ---
            if isinstance(image_bytes, bytes):
                img = Image.open(BytesIO(image_bytes))
            elif isinstance(image_bytes, str):
                img_bytes = base64.b64decode(image_bytes)
                img = Image.open(BytesIO(img_bytes))
            elif isinstance(image_bytes, Image.Image):
                img = image_bytes
            else:
                raise ValueError(f"Unsupported input type: {type(image_bytes)}")

            # --- Run inference ---
            result = self.inference_logic.infer_from_image(img, device_id)

            return {
                "device_id": result["device_id"],
                "dry_ratio": result["dry_ratio"],
                "decision": result["decision"],
                "confidence": result["confidence"],
                "patch_count": result["patch_count"],
                "duration_min": result.get("duration_min", 0),
                "latency_ms_model": result.get("latency_ms", 0),
                "ts": result.get("ts"),
                "idempotency_key": result.get("idempotency_key"),
                "debug": result.get("debug")
            }

        except Exception as e:
            logger.error(f"Inference failed: {e}", exc_info=True)
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "error": str(e),
                "device_id": locals().get("device_id", "unknown"),
                "latency_ms_model": latency_ms
            }