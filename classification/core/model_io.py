# core/model_io.py
# Core I/O and inference utilities for baseline audio classification.

from __future__ import annotations

import pathlib
import shutil
import subprocess
from typing import List, Optional, Dict, Tuple, Any

import numpy as np
import soundfile as sf
import librosa

try:
    import torch  # optional
except Exception:  # pragma: no cover
    torch = None  # type: ignore

from panns_inference import AudioTagging
from labels_map import bucket_of

# Recommended PANNs sample rate
SAMPLE_RATE = 32000
# Minimal padding for very short inputs (~0.5s @ 32kHz)
MIN_SAMPLES = 16000

# Formats typically hard for libsndfile (handled via librosa/ffmpeg first)
HARD_EXTS = {".mp3", ".opus", ".m4a", ".aac"}


# ---------- FFmpeg helpers ----------

def has_ffmpeg() -> bool:
    """Return True if ffmpeg is available in PATH."""
    return shutil.which("ffmpeg") is not None


def decode_with_ffmpeg_to_float32_mono(path: str, target_sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Decode media to mono float32 at target_sr using ffmpeg (must be installed).
    Produces raw float32 frames to stdout for zero-copy handoff.
    """
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", path,
        "-vn",
        "-ac", "1",
        "-ar", str(target_sr),
        "-f", "f32le",
        "pipe:1"
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    y = np.frombuffer(proc.stdout, dtype=np.float32)
    if y.size < MIN_SAMPLES:
        pad = np.zeros(MIN_SAMPLES - y.size, dtype=np.float32)
        y = np.concatenate([y, pad], axis=0)
    return y


# ---------- Files / Checkpoint ----------

def ensure_checkpoint(checkpoint_path: str, checkpoint_url: Optional[str]) -> str:
    """
    Ensure the weight file exists locally. If not present and a URL is provided,
    download it using urllib (no external tools).
    Returns the local filesystem path to the checkpoint.
    """
    import urllib.request

    p = pathlib.Path(checkpoint_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if p.exists():
        return str(p)

    if not checkpoint_url:
        raise FileNotFoundError(
            f"No checkpoint found at: {p}. Provide --checkpoint or --checkpoint-url."
        )

    print(f"[info] Downloading checkpoint:\n  URL: {checkpoint_url}\n  -> {p}")
    urllib.request.urlretrieve(checkpoint_url, p)  # nosec - controlled via CLI
    print("[info] Download complete.")
    return str(p)


# ---------- Audio Loading ----------

def load_audio(path: str, target_sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Load an audio file, convert to mono, resample to target_sr, and return float32 in [-1, 1].
    Strategy:
      - If extension is “hard” for libsndfile (e.g., .mp3/.opus/.m4a/.aac):
          Try librosa.load first (audioread/ffmpeg). If it fails, try ffmpeg fallback.
      - Else (easier formats like wav/flac/ogg/aiff/aif/au):
          Try soundfile first. If it fails, try librosa.load, then ffmpeg fallback.
    """
    ext = pathlib.Path(path).suffix.lower()

    def _pad_if_short(y: np.ndarray) -> np.ndarray:
        if y.size < MIN_SAMPLES:
            pad = np.zeros(MIN_SAMPLES - y.size, dtype=np.float32)
            y = np.concatenate([y, pad], axis=0)
        return y

    if ext in HARD_EXTS:
        try:
            y, _ = librosa.load(path, sr=target_sr, mono=True)
            y = np.asarray(y, dtype=np.float32)
            return _pad_if_short(y)
        except Exception:
            if has_ffmpeg():
                y = decode_with_ffmpeg_to_float32_mono(path, target_sr=target_sr)
                return _pad_if_short(y)
            raise

    try:
        y, sr = sf.read(path, always_2d=False)
        if hasattr(y, "ndim") and y.ndim > 1:
            y = np.mean(y, axis=1)
        y = np.asarray(y, dtype=np.float32)
        if int(sr) != int(target_sr):
            y = librosa.resample(y, orig_sr=int(sr), target_sr=int(target_sr))
        return _pad_if_short(y)
    except Exception:
        try:
            y, _ = librosa.load(path, sr=target_sr, mono=True)
            y = np.asarray(y, dtype=np.float32)
            return _pad_if_short(y)
        except Exception:
            if has_ffmpeg():
                y = decode_with_ffmpeg_to_float32_mono(path, target_sr=target_sr)
                return _pad_if_short(y)
            raise


# ---------- Labels ----------

def load_audioset_labels_from_pkg() -> Optional[List[str]]:
    """
    Attempt to read AudioSet label names from panns_inference resources/class_labels_indices.csv.
    Returns None if not available or on error.
    """
    try:
        import panns_inference, inspect, os, csv  # local import to keep top clean
        pkg_dir = os.path.dirname(inspect.getfile(panns_inference))
        csv_path = os.path.join(pkg_dir, "resources", "class_labels_indices.csv")
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if rows and "index" in rows[0]:
            rows.sort(key=lambda r: int(r["index"]))
        names = [(r.get("display_name") or r.get("name") or "").strip() for r in rows]
        return names or None
    except Exception:
        return None


def load_labels_from_csv(csv_path: str) -> Optional[List[str]]:
    """
    Read an external CSV identical to class_labels_indices.csv and return a list of names ordered by 'index'.
    """
    try:
        import csv
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if rows and "index" in rows[0]:
            rows.sort(key=lambda r: int(r["index"]))
        names = [(r.get("display_name") or r.get("name") or "").strip() for r in rows]
        return names or None
    except Exception:
        return None


# ---------- Inference ----------

def _to_numpy(x: Any) -> np.ndarray:
    """
    Convert torch.Tensor / lists to numpy.float32 safely.
    Accepts shapes: (C,), (1, C), (C, 1); returns 1D (C,).
    """
    if torch is not None and isinstance(x, torch.Tensor):  # type: ignore
        x = x.detach().cpu().numpy()
    arr = np.asarray(x, dtype=np.float32)
    if arr.ndim == 2:
        if arr.shape[0] == 1:
            arr = arr[0]
        elif arr.shape[1] == 1:
            arr = arr[:, 0]
        else:
            arr = arr.reshape(-1)
    elif arr.ndim != 1:
        arr = arr.reshape(-1)
    return arr


def run_inference(at: AudioTagging, wav: np.ndarray) -> Tuple[np.ndarray, List[str]]:
    """
    Run model inference robustly and return:
      - probs: 1D numpy array (num_classes,)
      - labels: list of class names
    """
    try:
        res = at.inference(wav)
    except Exception as e1:
        try:
            res = at.inference(wav[None, :])
        except Exception as e2:  # pragma: no cover
            raise RuntimeError(f"inference failed (1D & 2D): {e1} | {e2}") from e2

    clipwise: Optional[np.ndarray] = None
    labels: Optional[List[str]] = None

    if isinstance(res, dict):
        clipwise = _to_numpy(res.get("clipwise_output"))
        labels = res.get("labels")
    elif isinstance(res, tuple):
        if len(res) >= 1:
            clipwise = _to_numpy(res[0])
        if len(res) >= 3 and isinstance(res[2], (list, tuple)):
            labels = list(res[2])

    if clipwise is None:
        clipwise = _to_numpy(res)

    if labels is None and hasattr(at, "labels"):
        labels = at.labels  # type: ignore

    if labels is None:
        labels = load_audioset_labels_from_pkg() or [f"class_{i}" for i in range(clipwise.size)]

    if clipwise.ndim != 1:
        clipwise = clipwise.reshape(-1)

    return clipwise, labels  # probs are sigmoid-like in [0,1]


# ---------- Embeddings ----------

def run_embedding(at: AudioTagging, wav: np.ndarray) -> np.ndarray:
    """
    Extract a 1D embedding vector from the model.
    Supports both dict/tuple outputs. Returns np.ndarray shape (D,).
    """
    try:
        res = at.inference(wav)
    except Exception as e1:
        try:
            res = at.inference(wav[None, :])
        except Exception as e2:  # pragma: no cover
            raise RuntimeError(f"embedding inference failed (1D & 2D): {e1} | {e2}") from e2

    emb = None
    if isinstance(res, dict):
        emb = res.get("embedding", None)
    elif isinstance(res, tuple):
        if len(res) >= 2:
            emb = res[1]

    if emb is None:
        raise RuntimeError("No embedding returned by panns_inference (expected dict['embedding'] or tuple[1]).")

    emb = _to_numpy(emb)
    emb = emb.reshape(-1)
    return emb


# ---------- Bucketing / Summaries ----------

def summarize_buckets(topk_labels: List[Tuple[str, float]]) -> Dict[str, float]:
    """
    Group probabilities into 4 coarse buckets by summing probabilities of labels falling into each bucket.
    Normalizes the dictionary to sum to 1.0.
    """
    sums: Dict[str, float] = {"animal": 0.0, "vehicle": 0.0, "shotgun": 0.0, "other": 0.0}
    for label, prob in topk_labels:
        b = bucket_of(label)
        sums[b] += float(prob)

    total = sum(sums.values())
    if total > 0:
        for k in sums:
            sums[k] /= total
    return sums
