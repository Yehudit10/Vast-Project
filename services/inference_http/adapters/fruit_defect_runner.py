# import os, io
# from pathlib import Path
# from typing import Any, Dict, Optional

# from PIL import Image
# import torch

# # Core code imported from your fruit-defect module
# from models.fruit_defect.inference.infer_fruit_defect import (
#     load_model, get_preprocess, infer_single
# )

# # Local weights only
# WEIGHTS_PATH = Path(os.getenv("WEIGHTS_PATH", "/app/weights/fruit_cls_best.ts"))

# def _ensure_local_weights(p: Path) -> Path:
#     if not p.exists():
#         raise FileNotFoundError(f"Local weights not found at: {p}")
#     return p

# class FruitDefectRunner:
#     def __init__(self, model_tag: Optional[str] = None):
#         # Allows selecting a different weights file in future via extra/model_tag
#         weights_path = _ensure_local_weights(WEIGHTS_PATH)
#         self.model = load_model(weights_path)  
#         self.preprocess = get_preprocess()
#         self.device = "cuda" if torch.cuda.is_available() else "cpu"
#         self.model = self.model.to(self.device).eval()

#     def run(self, image_bytes: bytes, model_tag=None, extra=None) -> Dict[str, Any]:
#         img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
#         result = infer_single(self.model, img, self.preprocess, device=self.device)
#         # Normalize to standard HTTP response structure
#         return {
#             "label": result.get("status"),
#             "score": result.get("prob_defect"),
#             "confidence": result.get("confidence"),
#             "latency_ms_model": result.get("latency_ms_model"),
#         }
import os, io
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image
import torch

# Core code imported from your fruit-defect module
from models.fruit_defect.inference.infer_fruit_defect import (
    load_model, get_preprocess, infer_single
)

# Local weights only
WEIGHTS_PATH = Path(os.getenv("WEIGHTS_PATH", "/app/weights/fruit_cls_best.ts"))

def _ensure_local_weights(p: Path) -> Path:
    if not p.exists():
        raise FileNotFoundError(f"Local weights not found at: {p}")
    return p

class FruitDefectRunner:
    def __init__(self, model_tag: Optional[str] = None):
        # Allows selecting a different weights file in future via extra/model_tag
        weights_path = _ensure_local_weights(WEIGHTS_PATH)
        self.model = load_model(weights_path)  
        self.preprocess = get_preprocess()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = self.model.to(self.device).eval()
    
    def run(self, image_bytes: bytes, model_tag=None, extra=None) -> Dict[str, Any]:
        # Decode image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        result = infer_single(self.model, img, self.preprocess, device=self.device)
    
        # Extract bucket/key as received from upstream (camera inference)
        bucket = extra.get("bucket") if extra else None
        key = extra.get("key") if extra else None
    
        # Extract device_id + timestamp from filename
        base = os.path.basename(key) if key else ""
        device_id = None
        timestamp = None
    
        m = re.match(r"([a-zA-Z0-9-]+)_(\d{8}T\d{6}Z)", base)
        if m:
            device_id, timestamp = m.groups()
    
        # Build image_uri
        image_uri = f"s3://{bucket}/{key}" if bucket and key else None
    
        # Normalize output
        return {
            "ok": True,
            "team": "fruit",
            "bucket": bucket,
            "key": key,
            "image_uri": image_uri,
            "device_id": device_id,
            "timestamp": timestamp,
    
            "label": result.get("status"),
            "score": result.get("prob_defect"),
            "confidence": result.get("confidence"),
            "latency_ms_model": result.get("latency_ms_model"),
        }
