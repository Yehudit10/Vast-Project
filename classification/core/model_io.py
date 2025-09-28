from __future__ import annotations

import pathlib
import shutil
import subprocess
from typing import Any, List, Optional, Tuple, Literal

import numpy as np
import soundfile as sf
import librosa
import logging
import os

try:
    import torch
except Exception:
    torch = None  # type: ignore
from panns_inference import AudioTagging

LOGGER = logging.getLogger(__name__)

SAMPLE_RATE = 32000
MIN_SAMPLES = 16000
HARD_EXTS = {".mp3", ".opus", ".m4a", ".aac", ".wma"}
SUPPORTED_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}

def ensure_numpy_1d(x):
    """
    Force input to be numpy float32 vector (1-D).
    Accepts numpy, torch.Tensor, TF tensors, and torch-like wrappers (duck-typed).
    """
    # Torch-like (duck typing): has detach/cpu/numpy
    if not isinstance(x, np.ndarray):
        has_detach = hasattr(x, "detach")
        has_cpu = hasattr(x, "cpu")
        has_numpy = hasattr(x, "numpy")
        if has_detach and has_cpu and has_numpy:
            try:
                x = x.detach().cpu().numpy()
            except Exception:
                pass
        # Generic tensors (e.g., TF), expose .numpy() without detach/cpu
        elif has_numpy and callable(getattr(x, "numpy", None)):
            try:
                x = x.numpy()
            except Exception:
                pass

    # Final conversion to numpy float32
    x = np.asarray(x, dtype=np.float32)

    # Flatten to 1-D
    if x.ndim > 1:
        x = x.reshape(-1)
    return x


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def decode_with_ffmpeg_to_float32_mono(path: str, target_sr: int = SAMPLE_RATE) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(target_sr), "-f", "f32le", "pipe:1"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    y = np.frombuffer(proc.stdout, dtype=np.float32)
    if y.size < MIN_SAMPLES:
        y = np.concatenate([y, np.zeros(MIN_SAMPLES - y.size, dtype=np.float32)], axis=0)
    return y


def ensure_checkpoint(checkpoint_path: str, checkpoint_url: Optional[str]) -> str:
    import urllib.request
    p = pathlib.Path(checkpoint_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return str(p)
    if not checkpoint_url:
        raise FileNotFoundError(f"No checkpoint at {p}. Provide --checkpoint or --checkpoint-url.")
    urllib.request.urlretrieve(checkpoint_url, p)  # nosec
    LOGGER.info("downloaded checkpoint to %s", p)
    return str(p)

def load_audio(path: str, target_sr: int = SAMPLE_RATE) -> np.ndarray:
    ext = pathlib.Path(path).suffix.lower()

    def _pad(y: np.ndarray) -> np.ndarray:
        if y.size < MIN_SAMPLES:
            y = np.concatenate([y, np.zeros(MIN_SAMPLES - y.size, dtype=np.float32)])
        return y

    # Compressed/streaming formats first (e.g., mp3, m4a, etc.)
    if ext in HARD_EXTS:
        try:
            y, _ = librosa.load(path, sr=target_sr, mono=True)
            y = ensure_numpy_1d(y)
            return _pad(y)
        except Exception:
            if has_ffmpeg():
                LOGGER.warning("librosa failed; using ffmpeg fallback for %s", path)
                y = decode_with_ffmpeg_to_float32_mono(path, target_sr)
                y = ensure_numpy_1d(y)
                return _pad(y)
            LOGGER.exception("failed to load compressed audio: %s", path)
            raise

    # Uncompressed / common wavs
    try:
        y, sr = sf.read(path, always_2d=False)
        # to mono if needed
        if hasattr(y, "ndim") and y.ndim > 1:
            y = np.mean(y, axis=1)

        y = ensure_numpy_1d(y)  # guarantees float32 1-D
        if int(sr) != int(target_sr):
            # librosa.resample may return float64; coerce afterwards
            y = librosa.resample(y, orig_sr=int(sr), target_sr=int(target_sr))
            y = ensure_numpy_1d(y)

        return _pad(y)

    except Exception:
        try:
            y, _ = librosa.load(path, sr=target_sr, mono=True)
            y = ensure_numpy_1d(y)
            return _pad(y)
        except Exception:
            if has_ffmpeg():
                LOGGER.warning("soundfile/librosa failed; using ffmpeg fallback for %s", path)
                y = decode_with_ffmpeg_to_float32_mono(path, target_sr)
                y = ensure_numpy_1d(y)
                return _pad(y)
            LOGGER.exception("failed to load audio: %s", path)
            raise


def load_audioset_labels_from_pkg() -> Optional[List[str]]:
    try:
        import panns_inference, inspect, os, csv
        pkg_dir = os.path.dirname(inspect.getfile(panns_inference))
        csv_path = os.path.join(pkg_dir, "resources", "class_labels_indices.csv")
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if rows and "index" in rows[0]:
            rows.sort(key=lambda r: int(r["index"]))
        return [(r.get("display_name") or r.get("name") or "").strip() for r in rows] or None
    except Exception:
        LOGGER.debug("failed to load labels from pkg", exc_info=True)
        return None


def load_labels_from_csv(csv_path: str) -> Optional[List[str]]:
    try:
        import csv
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if rows and "index" in rows[0]:
            rows.sort(key=lambda r: int(r["index"]))
        return [(r.get("display_name") or r.get("name") or "").strip() for r in rows] or None
    except Exception:
        LOGGER.debug("failed to load labels csv: %s", csv_path, exc_info=True)
        return None


def _to_numpy(x: Any) -> np.ndarray:
    if (torch is not None) and hasattr(torch, "Tensor") and isinstance(x, torch.Tensor):  # type: ignore
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
    try:
        res = at.inference(wav)
    except Exception:
        res = at.inference(wav[None, :])

    clipwise: Optional[np.ndarray] = None
    labels: Optional[List[str]] = None

    if isinstance(res, dict):
        clipwise = _to_numpy(res.get("clipwise_output"))
        raw_labels = res.get("labels")
        if isinstance(raw_labels, (list, tuple)):
            labels = [str(x) for x in raw_labels]
    elif isinstance(res, tuple):
        if len(res) >= 1:
            clipwise = _to_numpy(res[0])
        if len(res) >= 3 and isinstance(res[2], (list, tuple)):
            labels = [str(x) for x in res[2]]

    if clipwise is None:
        clipwise = _to_numpy(res)

    clipwise = clipwise.reshape(-1).astype(np.float32, copy=False)
    if np.isnan(clipwise).any() or np.isinf(clipwise).any():
        clipwise = np.nan_to_num(clipwise, nan=0.0, posinf=1.0, neginf=0.0)

    if labels is None and hasattr(at, "labels"):
        try:
            labels = [str(x) for x in list(at.labels)]  # type: ignore[attr-defined]
        except Exception:
            labels = None

    if labels is None:
        labels = load_audioset_labels_from_pkg() or [f"class_{i}" for i in range(clipwise.size)]
    if len(labels) != clipwise.size:
        labels = [f"class_{i}" for i in range(clipwise.size)]

    return clipwise, labels


def segment_waveform(
    wav: np.ndarray,
    sr: int = SAMPLE_RATE,
    window_sec: float = 2.0,
    hop_sec: float = 0.5,
    pad_last: bool = True,
) -> List[Tuple[float, float, np.ndarray]]:
    wav = np.asarray(wav, dtype=np.float32).reshape(-1)
    win = max(1, int(round(window_sec * sr)))
    hop = max(1, int(round(hop_sec * sr)))
    n = wav.size

    segments: List[Tuple[float, float, np.ndarray]] = []
    if n == 0:
        return segments

    i = 0
    while i + win <= n:
        seg = wav[i: i + win]
        t0 = i / sr
        t1 = (i + win) / sr
        segments.append((t0, t1, seg))
        i += hop

    if pad_last and (i < n):
        tail = wav[i:]
        pad = np.zeros(win - tail.size, dtype=np.float32)
        seg = np.concatenate([tail, pad], axis=0)
        t0 = i / sr
        t1 = (i + win) / sr
        segments.append((t0, t1, seg))
    elif not segments and pad_last:
        pad = np.zeros(win - n, dtype=np.float32)
        seg = np.concatenate([wav, pad], axis=0)
        segments.append((0.0, win / sr, seg))

    return segments


def run_inference_with_embedding(at: AudioTagging, wav: np.ndarray) -> Tuple[np.ndarray, List[str], Optional[np.ndarray]]:
    try:
        res = at.inference(wav)
    except Exception:
        res = at.inference(wav[None, :])

    clipwise = None
    labels: Optional[List[str]] = None
    embedding = None

    if isinstance(res, dict):
        clipwise = _to_numpy(res.get("clipwise_output"))
        embedding = res.get("embedding", None)
        raw_labels = res.get("labels")
        if isinstance(raw_labels, (list, tuple)):
            labels = [str(x) for x in raw_labels]
    elif isinstance(res, tuple):
        if len(res) >= 1:
            clipwise = _to_numpy(res[0])
        if len(res) >= 2:
            embedding = res[1]
        if len(res) >= 3 and isinstance(res[2], (list, tuple)):
            labels = [str(x) for x in res[2]]

    if clipwise is None:
        clipwise = _to_numpy(res)

    clipwise = clipwise.reshape(-1).astype(np.float32, copy=False)
    if np.isnan(clipwise).any() or np.isinf(clipwise).any():
        clipwise = np.nan_to_num(clipwise, nan=0.0, posinf=1.0, neginf=0.0)

    if labels is None and hasattr(at, "labels"):
        try:
            labels = [str(x) for x in list(at.labels)]  # type: ignore[attr-defined]
        except Exception:
            labels = None
    if labels is None:
        labels = load_audioset_labels_from_pkg() or [f"class_{i}" for i in range(clipwise.size)]
    if len(labels) != clipwise.size:
        labels = [f"class_{i}" for i in range(clipwise.size)]

    emb_out: Optional[np.ndarray] = None
    if embedding is not None:
        try:
            emb_out = _to_numpy(embedding).reshape(-1).astype(np.float32, copy=False)
            if np.isnan(emb_out).any() or np.isinf(emb_out).any():
                emb_out = np.nan_to_num(emb_out, nan=0.0, posinf=0.0, neginf=0.0)
        except Exception:
            emb_out = None

    return clipwise, labels, emb_out


def aggregate_matrix(mat: np.ndarray, mode: Literal["mean", "max"] = "mean") -> np.ndarray:
    if not isinstance(mat, np.ndarray):
        raise TypeError("mat must be a numpy.ndarray")
    if mat.ndim != 2:
        raise ValueError("expected shape (num_windows, num_classes)")
    if mat.shape[0] == 0:
        raise ValueError("cannot aggregate an empty window matrix (num_windows == 0)")
    if mat.shape[1] == 0:
        raise ValueError("expected num_classes > 0")
    if mode == "mean":
        # Ignore NaNs when computing per-class means
        v = np.nanmean(mat.astype(np.float32, copy=False), axis=0)
    elif mode == "max":
        # Ignore NaNs when computing per-class max
        v = np.nanmax(mat.astype(np.float32, copy=False), axis=0)
    else:
        raise ValueError(f"Unsupported aggregation mode: {mode}")

    # Ensure finite float32 output; all-NaN columns become 0.0
    v = np.nan_to_num(v, nan=0.0, posinf=np.finfo(np.float32).max, neginf=np.finfo(np.float32).min)
    return v.astype(np.float32, copy=False)


def discover_audio_files(root: pathlib.Path) -> List[pathlib.Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_EXTS else []
    files: List[pathlib.Path] = []
    for ext in SUPPORTED_EXTS:
        files.extend(root.rglob(f"*{ext}"))
    return sorted(files)


def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def softmax_1d(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    if x.size == 0:
        return x
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    m = float(np.max(x))
    y = np.exp(x - m)
    s = float(np.sum(y))
    if not np.isfinite(s) or s <= 0.0:
        return np.full_like(x, 1.0 / x.size)
    return y / s

