# services/inference_http/adapters/rover_runner.py
# Bridge between unified HTTP /infer_json and fence_hole_detector service logic.

from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime
import json
import logging

from models.fence_hole_detector.service import InferenceInput, infer_from_minio

logger = logging.getLogger(__name__)


def _to_plain_dict(obj: Any) -> Any:
    """Best-effort conversion of arbitrary objects to a plain dict or JSON-like object."""
    if isinstance(obj, (dict, str, bytes, bytearray)):
        return obj

    # Pydantic v2 models
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass

    # Pydantic v1 or similar objects
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass

    # Generic Python objects with __dict__
    if hasattr(obj, "__dict__"):
        try:
            return vars(obj)
        except Exception:
            pass

    return obj


def _search_bucket_key(node: Any) -> Optional[Dict[str, Any]]:
    """
    Recursively search for a dict that contains both 'bucket' and 'key'.

    This walks nested dicts and lists/tuples and returns the first match.
    """
    node = _to_plain_dict(node)

    if isinstance(node, dict):
        if "bucket" in node and "key" in node:
            return node

        for value in node.values():
            found = _search_bucket_key(value)
            if found is not None:
                return found

    elif isinstance(node, (list, tuple)):
        for item in node:
            found = _search_bucket_key(item)
            if found is not None:
                return found

    return None


def _extract_payload(obj: Any) -> Dict[str, Any]:
    """
    Normalize a generic event/envelope into a flat dict with bucket/key.

    Supports:
      - {"bucket": "...", "key": "...", ...}
      - {"event": {...}}, {"data": {...}}, etc.
      - Pydantic models, nested dicts, lists
      - JSON strings/bytes
    """
    obj = _to_plain_dict(obj)

    # If this is a JSON string or bytes, try to parse it.
    if isinstance(obj, (str, bytes, bytearray)):
        try:
            obj = json.loads(obj)
        except Exception:
            logger.warning("rover_runner: failed to json.loads extra payload: %r", obj)
            return {}

    # For dicts/lists/tuples, search for bucket/key recursively.
    if isinstance(obj, (dict, list, tuple)):
        found = _search_bucket_key(obj)
        if isinstance(found, dict):
            return found

        # As a fallback, if this is a dict without bucket/key, just return it.
        if isinstance(obj, dict):
            return obj

    return {}


class RoverRunner:
    """
    Adapter that executes the fence_hole_detector service logic.

    The unified HTTP layer usually:
      1. Parses the JSON body into a dict.
      2. Downloads the image bytes from MinIO.
      3. Calls runner.run(image_bytes, extra=parsed_body).

    We ignore the image bytes and call infer_from_minio again using bucket/key
    from the extra payload, so the existing service code does not need changes.
    """

    def __init__(self, weights_path: Optional[str] = None,
                 model_tag: Optional[str] = None) -> None:
        # Weights are controlled via FENCE_ONNX_PATH env var inside the service.
        self.model_tag = model_tag or "yolov8n-onnx"

    def run(
        self,
        image_bytes: Optional[bytes] = None,
        model_tag: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Main entrypoint for the unified /infer_json service.

        Expected call pattern:
          run(image_bytes=<image-from-minio>, extra=<original JSON event/body>)

        We:
          - Extract bucket/key (and optional metadata) from extra.
          - Build InferenceInput and call infer_from_minio().
          - Attach a standard 'model' field to the result.
        """
        logger.info(
            "RoverRunner.run: got image_bytes_type=%s extra=%r",
            type(image_bytes),
            extra,
        )

        payload: Dict[str, Any] = _extract_payload(extra or {})
        logger.info("RoverRunner.run: extracted payload=%r", payload)

        # Accept common alternative field names as a backup.
        bucket = payload.get("bucket") or payload.get("s3_bucket")
        key = payload.get("key") or payload.get("s3_key") or payload.get("object_key")

        if not bucket or not key:
            msg = f"Missing required fields: bucket/key in payload={payload!r}"
            logger.error("RoverRunner.run: %s", msg)
            raise ValueError(msg)

        # Optional metadata: timestamp and geo / device info.
        ts = payload.get("captured_at")
        captured_at: Optional[datetime] = None
        if ts:
            try:
                captured_at = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except Exception:
                captured_at = None

        inp = InferenceInput(
            bucket=bucket,
            key=key,
            captured_at=captured_at,
            device_id=payload.get("device_id"),
            area=payload.get("area"),
            lat=payload.get("lat"),
            lon=payload.get("lon"),
        )

        result = infer_from_minio(inp)
        result["model"] = self.model_tag
        return result
