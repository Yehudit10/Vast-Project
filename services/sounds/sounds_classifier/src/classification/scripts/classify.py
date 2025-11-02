from __future__ import annotations

from cProfile import label
import logging
import os
import tempfile
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple, Any
from panns_inference import AudioTagging
import numpy as np
import joblib

from minio import Minio
from minio.error import S3Error
import re
from datetime import datetime, timezone
import uuid

from classification.core.model_io import (
    SAMPLE_RATE,
    _to_numpy,
    load_audio,           # returns 1-D float32 mono @ SAMPLE_RATE
    # segment_waveform,     # returns List[np.ndarray] after our fix
    segment_waveform_2d_view,
    aggregate_matrix,
)
from classification.backbones.cnn14 import load_cnn14_model, run_cnn14_embedding, run_cnn14_embeddings_batch
from classification.scripts import alerts

# -----------------------------
# Environment configuration
# -----------------------------
DEVICE = os.getenv("DEVICE", "cpu").strip().lower()
BACKBONE = os.getenv("BACKBONE", "cnn14").strip().lower()

CHECKPOINT = os.getenv("CHECKPOINT") or ""
CHECKPOINT_URL = os.getenv("CHECKPOINT_URL") or ""

HEAD_PATH = os.getenv("HEAD") or ""            # joblib path
LABELS_CSV = os.getenv("LABELS_CSV") or ""     # optional (if head has classes_, not needed)

WINDOW_SEC = float(os.getenv("WINDOW_SEC", "2.0"))
HOP_SEC = float(os.getenv("HOP_SEC", "0.5"))
PAD_LAST = os.getenv("PAD_LAST", "true").strip().lower() in ("1", "true", "yes", "on")
AGG = os.getenv("AGG", "mean").strip().lower()  # "mean" | "max"

UNKNOWN_THRESHOLD = float(os.getenv("UNKNOWN_THRESHOLD", "0.55"))

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minio123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").strip().lower() in ("1", "true", "yes", "on")

ALLOWED_BUCKETS: List[str] = [b.strip() for b in os.getenv("ALLOWED_BUCKETS", "").split(",") if b.strip()]
ALLOWED_CONTENT_TYPES: List[str] = [t.strip() for t in os.getenv(
    "ALLOWED_CONTENT_TYPES",
    "audio/wav,audio/x-wav,audio/mpeg,audio/flac,audio/ogg,audio/mp4"
).split(",") if t.strip()]
MAX_BYTES = int(os.getenv("MAX_BYTES", str(50 * 1024 * 1024)))

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka:9092")
ALERTS_TOPIC = os.getenv("ALERTS_TOPIC", "alerts")

# -----------------------------
# Lazy runtime (model/head/labels)
# -----------------------------
class _Runtime:
    model = None   # CNN14 backbone
    head = None    # sklearn pipeline with predict_proba
    classes: List[str] = []  # class names aligned to head output

R = _Runtime()

_MINIO_CLIENT = None

def _get_minio():
    global _MINIO_CLIENT
    if _MINIO_CLIENT is None:
        _MINIO_CLIENT = Minio(
            MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=MINIO_SECURE
        )
    return _MINIO_CLIENT

_TS_PATTERNS = (
    # ISO-like with Z or without Z, with or without 'T'
    r"(?P<iso>\d{4}-?\d{2}-?\d{2}[T ]?\d{2}:?\d{2}:?\d{2}Z?)",
    # Compact: YYYYMMDDTHHMMSSZ or YYYYMMDDHHMMSS
    r"(?P<compact>\d{8}T?\d{6}Z?)",
    # Epoch seconds or millis
    r"(?P<epoch>\d{10}|\d{13})",
)

def _parse_started_at_from_token(token: str) -> Optional[str]:
    """Return ISO8601 UTC Z string if token looks like a timestamp; else None."""
    t = token.strip()
    # epoch
    if re.fullmatch(r"\d{13}", t):
        dt = datetime.fromtimestamp(int(t)/1000.0, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if re.fullmatch(r"\d{10}", t):
        dt = datetime.fromtimestamp(int(t), tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    # compact YYYYMMDD[ T]?HHMMSS[Z]?
    m = re.fullmatch(r"(\d{8})T?(\d{6})Z?", t)
    if m:
        d, h = m.groups()
        dt = datetime.strptime(d + h, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    # ISO-ish (allow missing separators)
    # normalize: keep only digits and Z, then rebuild
    if re.fullmatch(r"\d{4}-?\d{2}-?\d{2}[T ]?\d{2}:?\d{2}:?\d{2}Z?", t):
        # try a few formats
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S", "%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
            try:
                if t.endswith("Z") and fmt.endswith("Z"):
                    dt = datetime.strptime(t.replace(" ", "T"), fmt).replace(tzinfo=timezone.utc)
                    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                if not t.endswith("Z") and not fmt.endswith("Z"):
                    dt = datetime.strptime(t.replace(" ", "T").replace("-", "").replace(":", ""), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
                    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass
    return None

def _extract_device_and_started_at_from_key(s3_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Expect filenames like 'sensorId_timestamp.*' (timestamp token can be in a few formats).
    Return (device_id, started_at_isoZ) or (None, None) if not confident.
    """
    name = Path(s3_key).name
    m = re.match(r"(?P<dev>[^_/]+)_(?P<ts>[^_.]+)", name)
    if not m:
        return None, None
    device_id = m.group("dev").strip()
    ts_token = m.group("ts").strip()
    started_at = _parse_started_at_from_token(ts_token)
    if not device_id or not started_at:
        return None, None
    return device_id, started_at

def _load_backbone_once() -> None:
    if R.model is not None:
        return
    if BACKBONE != "cnn14":
        raise RuntimeError(f"Only BACKBONE=cnn14 is supported in this service, got {BACKBONE}")
    # load_cnn14_model internally handles checkpoint/url (your impl)
    R.model = load_cnn14_model(CHECKPOINT or None, device=DEVICE)

def _load_head_once() -> None:
    if R.head is not None:
        return
    if not HEAD_PATH:
        raise RuntimeError("HEAD env var is required (path to joblib head)")
    R.head = joblib.load(HEAD_PATH)
    if not hasattr(R.head, "predict_proba"):
        raise RuntimeError("HEAD must expose predict_proba(X) and classes_)")

    # 1) try labels from CSV if provided (most robust for production)
    labels_csv = os.getenv("LABELS_CSV") or ""
    if labels_csv:
        from classification.core.model_io import load_labels_from_csv
        labels = load_labels_from_csv(labels_csv)
        if not labels:
            raise RuntimeError(f"Labels CSV is empty or unreadable: {labels_csv}")
        R.classes = labels
        return

    # 2) else, try meta.json next to HEAD (HEAD_META env or HEAD+'.meta.json')
    head_meta = os.getenv("HEAD_META") or (HEAD_PATH + ".meta.json")
    labels_from_meta = []
    try:
        if os.path.exists(head_meta):
            import json
            with open(head_meta, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if isinstance(meta.get("class_order"), list) and len(meta["class_order"]) > 0:
                labels_from_meta = [str(x) for x in meta["class_order"]]
    except Exception as e:
        print(f"⚠️ Warning: failed to parse HEAD meta: {e}")

    # 3) reconcile with head.classes_
    head_classes = list(getattr(R.head, "classes_", []))
    if labels_from_meta:
        # if head.classes_ are [0..N-1], we map by index
        if all(isinstance(c, (int, np.integer)) for c in head_classes):
            if len(head_classes) != len(labels_from_meta):
                raise RuntimeError(
                    f"Meta class_order length ({len(labels_from_meta)}) != head.classes_ length ({len(head_classes)})"
                )
            R.classes = labels_from_meta
            return
        # else: if head.classes_ already hold real names, prefer them
        R.classes = [str(c) for c in head_classes] if head_classes else labels_from_meta
        return

    # 4) fallback to head.classes_ as strings
    if head_classes:
        R.classes = [str(c) for c in head_classes]
        return

    # 5) no labels source found
    raise RuntimeError(
        "No labels source found. Provide LABELS_CSV, or HEAD_META with class_order, "
        "or ensure the head exposes string class names via classes_."
    )

# -----------------------------
# Embedding/inference helpers
# -----------------------------

def _aggregate_probs(per_window_probs: np.ndarray) -> np.ndarray:
    """
    Aggregate per-window class probabilities to a single clip-level vector.
    Supports mean|max; returns 1-D float32.
    """
    if per_window_probs.ndim != 2:
        raise ValueError("expected shape (num_windows, num_classes)")
    if per_window_probs.shape[0] == 0:
        return np.zeros((per_window_probs.shape[1],), dtype=np.float32)
    v = aggregate_matrix(per_window_probs, mode=AGG)
    # When AGG=max, v might be logits-like — but we trained on probs, so it is already probabilities.
    # If needed: apply softmax here. For a calibrated head (sklearn) it's already in [0,1].
    return v.astype(np.float32, copy=False)

# -----------------------------
# Public API for service
# -----------------------------

# Create a dedicated logger for performance metrics
perf_logger = logging.getLogger("audio_cls.perf")
perf_logger.setLevel(logging.INFO)
if not perf_logger.handlers:
    h = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] [PERF] %(message)s", "%Y-%m-%d %H:%M:%S")
    h.setFormatter(fmt)
    perf_logger.addHandler(h)

def classify_file(
    path: str,
    pann_model: Optional[AudioTagging] = None,
    sk_pipeline: Optional[Any] = None
) -> Dict[str, object]:
    t0 = time.perf_counter()
    if sk_pipeline is None:
        _load_head_once()
    if pann_model is None:
        _load_backbone_once()

    wav = np.array(load_audio(path, SAMPLE_RATE), dtype=np.float32, copy=True, order="C")
    windows_2d = segment_waveform_2d_view(
        wav, SAMPLE_RATE, window_sec=WINDOW_SEC, hop_sec=HOP_SEC, pad_last=PAD_LAST
    )
    
    num_windows = int(windows_2d.shape[0])
    if num_windows == 0:
        result = {
            "label": "another",
            "probs": {c: 0.0 for c in R.classes},
            "pred_prob": 0.0,
            "unknown_threshold": UNKNOWN_THRESHOLD,
            "is_another": True,
            "num_windows": 0,
            "agg_mode": AGG,
            "processing_ms": int((time.perf_counter() - t0) * 1000.0),
        }
        return result

    # Batch embeddings
    if pann_model is not None:
        win = np.array(windows_2d, dtype=np.float32, copy=True, order="C")
        seg = pann_model.inference(win)
        if isinstance(seg, dict):
            seg = seg.get("embedding")
        elif isinstance(seg, tuple) and len(seg) >= 2:
            seg = seg[1]
        seg = np.asarray(seg, dtype=np.float32)
        if seg.ndim == 1:
            seg = seg[None, :]
    else:
        win = np.array(windows_2d, dtype=np.float32, copy=True, order="C")
        seg = run_cnn14_embeddings_batch(R.model, win, batch_size=32)

    # Head predict_proba
    clf = sk_pipeline if sk_pipeline is not None else R.head
    per_window_probs = np.asarray(clf.predict_proba(seg), dtype=np.float32)

    # Aggregate and finalize
    agg_vec = _aggregate_probs(per_window_probs)
    k = int(np.argmax(agg_vec))
    top_prob = float(agg_vec[k])
    top_label = R.classes[k]
    final_label = top_label if top_prob >= UNKNOWN_THRESHOLD else "another"
    probs = {cls: float(p) for cls, p in zip(R.classes, agg_vec)}

    processing_ms = int((time.perf_counter() - t0) * 1000.0)

    return {
        "label": final_label,
        "probs": probs,
        "pred_prob": top_prob,
        "unknown_threshold": UNKNOWN_THRESHOLD,
        "is_another": (final_label == "another"),
        "num_windows": num_windows,
        "agg_mode": AGG,
        "processing_ms": processing_ms,
    }

def run_classification_job(
    *,
    s3_bucket: str,
    s3_key: str,
    pann_model: Optional[AudioTagging] = None,  
    sk_pipeline: Optional[Any] = None            
) -> Dict[str, object]:
    """
    Download from MinIO → classify_file → (optional) Kafka alert.
    Returns a dict with 'label', 'probs, and alert send status.
    """
    _load_head_once()
    if ALLOWED_BUCKETS and s3_bucket not in ALLOWED_BUCKETS:
        raise RuntimeError(f"Bucket '{s3_bucket}' is not allowed")

    client = _get_minio()

    # stat & validate
    try:
        stat = client.stat_object(s3_bucket, s3_key)
    except S3Error as e:
        raise RuntimeError(f"S3 stat failed: {e}") from e
    size = getattr(stat, "size", None)
    ctype = getattr(stat, "content_type", "") or ""
    if size and size > MAX_BYTES:
        raise RuntimeError(f"Object too large: {size} > {MAX_BYTES}")
    if ctype and ALLOWED_CONTENT_TYPES and ctype not in ALLOWED_CONTENT_TYPES:
        raise RuntimeError(f"Unsupported content-type: {ctype}")

    # download to temp
    suffix = Path(s3_key).suffix or ".wav"
    fd, tmp_path = tempfile.mkstemp(prefix="audio_", suffix=suffix)
    os.close(fd)
    try:
        client.fget_object(s3_bucket, s3_key, tmp_path)
        result = classify_file(tmp_path, pann_model=pann_model, sk_pipeline=sk_pipeline)
        # default alert flags
        result.setdefault("sent_alert", False)
        result.setdefault("alert_topic", None)
        result.setdefault("alert_skip_reason", None)
        if result.get("processing_ms") is not None:
            try:
                result["processing_ms"] = int(result["processing_ms"])
            except Exception:
                pass
        if result["label"] != "another" and KAFKA_BROKERS and ALERTS_TOPIC:
            device_id, started_at = _extract_device_and_started_at_from_key(s3_key)
            if device_id and started_at:
                try:
                    label = str(result["label"])
                    alert_type = f"suspicious_sound-{label}"

                    severity = None
                    sev_map_env = os.getenv("ALERT_SEVERITY_MAP", "").strip()
                    if sev_map_env:
                        try:
                            _sev_map = __import__("json").loads(sev_map_env)
                            if isinstance(_sev_map, dict) and label in _sev_map:
                                _s = _sev_map[label]
                                if isinstance(_s, (int, np.integer)):
                                    severity = int(_s)
                        except Exception:
                            pass
                    
                    confidence = float(result.get("pred_prob") or 0.0)
                    
                    meta = {
                        "bucket": s3_bucket,
                        "key": s3_key,
                        "processing_ms": result.get("processing_ms"),
                    }
                    if meta["processing_ms"] is None:
                        meta.pop("processing_ms")
                    message_key = f"{device_id}|{started_at}"
                    
                    ok = alerts.send_structured_alert(
                        brokers=KAFKA_BROKERS,
                        topic=ALERTS_TOPIC,
                        alert_type=alert_type,
                        device_id=device_id,
                        started_at=started_at,
                        confidence=confidence,
                        severity=severity,
                        meta=meta,
                        message_key=message_key,
                    )
                    perf_logger.info("About to send alert: topic=%s key=%s type=%s",
                                     ALERTS_TOPIC, message_key, alert_type)
                    if ok:
                        result["sent_alert"] = True
                        result["alert_topic"] = ALERTS_TOPIC
                    else:
                        perf_logger.warning("Alert send returned False (topic=%s key=%s)", ALERTS_TOPIC, s3_key)
                        result["alert_skip_reason"] = "kafka_produce_returned_false"
                except Exception as e:
                    perf_logger.warning("Alert send failed: %s (key=%s)", e, s3_key)
                    result["alert_skip_reason"] = "kafka_exception"
            else:
                perf_logger.warning(
                    "Skip alert (missing device_id/started_at) for key=%s", s3_key
                )
                result["alert_skip_reason"] = "missing_device_or_started_at"
        elif result["label"] == "another":
            result["alert_skip_reason"] = "label_is_another"
        elif not KAFKA_BROKERS or not ALERTS_TOPIC:
            result["alert_skip_reason"] = "missing_env_brokers_or_topic"
        return result
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
