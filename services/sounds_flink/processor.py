import json
import logging
from datetime import datetime
from typing import Tuple, Optional, Dict
from urllib.parse import unquote, unquote_plus

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    CLASSIFIER_HTTP_URL,
    REQUEST_TIMEOUT,
    RETRIES_TOTAL,
    BACKOFF_FACTOR,
    DEFAULT_BUCKET,
)

# Reusable HTTP session with retries/backoff
_session = requests.Session()
_retries = Retry(
    total=RETRIES_TOTAL,
    backoff_factor=BACKOFF_FACTOR,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=["GET", "POST"],
    respect_retry_after_header=True,
)
_session.mount("http://", HTTPAdapter(max_retries=_retries))
_session.mount("https://", HTTPAdapter(max_retries=_retries))


def _try_json(raw: str) -> Optional[Dict]:
    try:
        return json.loads(raw)
    except Exception:
        return None


def _extract_bucket_key(event: Dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract (bucket, key) from multiple possible MinIO/S3 event shapes.
    Supports:
      - short link format: {"file_name": "...", "key": "<bucket>/<path>", "linked_time": "..."}
      - flat: {"Bucket": "...", "Key": "..."}
      - Records[0].s3.bucket.name / Records[0].s3.object.key
    """
    bucket: Optional[str] = None
    key: Optional[str] = None

    # 1) Short link format (from *_connections topics): key="<bucket>/<object-path>"
    if isinstance(event.get("key"), str):
        k = event["key"].strip()
        k = unquote_plus(unquote(k))
        if "/" in k:
            bucket, key = k.split("/", 1)
        else:
            key = k  # no bucket provided here

    # 2) Flat shape
    if (bucket is None or key is None) and event.get("Bucket") and event.get("Key"):
        bucket = bucket or event.get("Bucket")
        key = key or event.get("Key")

    # 3) Records[...] S3-style
    if bucket is None or key is None:
        records = event.get("Records") or []
        if records:
            r0 = records[0]
            s3 = r0.get("s3", {})
            b = s3.get("bucket", {})
            o = s3.get("object", {})
            bucket = bucket or b.get("name")
            key = key or o.get("key")

    # Normalize/URL-decode
    if isinstance(key, str) and key:
        key = unquote_plus(unquote(key))

    return bucket, key


def _classify(bucket: Optional[str], key: Optional[str]) -> Optional[Dict]:
    """
    Call the classifier service with the resolved (bucket, key).
    The classifier expects:
      { "s3_bucket": "...", "s3_key": "..." }
    """
    if not key:
        return None

    # Prefer provided bucket, otherwise fallback to DEFAULT_BUCKET if configured
    eff_bucket = bucket or (DEFAULT_BUCKET if DEFAULT_BUCKET else None)
    if not eff_bucket:
        # Without a bucket we cannot call the classifier
        return None

    payload = {
        "s3_bucket": eff_bucket,
        "s3_key": key,
    }

    try:
        resp = _session.post(CLASSIFIER_HTTP_URL, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code >= 400:
            logging.warning("Classifier returned %s for key=%s", resp.status_code, key)
            return None
        return resp.json()
    except Exception as e:
        logging.warning("Classifier request failed for key=%s: %s", key, e)
        return None


def process_json_line(raw: str) -> str:
    """
    Map function: input raw JSON string -> output JSON string or "" to skip.
    1) Parse JSON
    2) Extract (bucket, key)
    3) Call classifier (payload: s3_bucket/s3_key)
    4) Return compact JSON result or "" to drop
    """
    event = _try_json(raw)
    if not event:
        return ""

    bucket, key = _extract_bucket_key(event)
    result = _classify(bucket, key)
    if not result:
        return ""

    out = {
        "s3_bucket": bucket or DEFAULT_BUCKET or "",
        "s3_key": key,
        "result": result,
        "received_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    return json.dumps(out, separators=(",", ":"))
