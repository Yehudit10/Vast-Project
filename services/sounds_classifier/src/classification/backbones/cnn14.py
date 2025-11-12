from __future__ import annotations
from typing import Tuple, List, Optional
import numpy as np
from panns_inference import AudioTagging
from classification.core.model_io import _to_numpy, ensure_checkpoint

def load_cnn14_model(
    checkpoint_path: Optional[str] = None,
    checkpoint_url: Optional[str] = None,
    device: str = "cpu"
) -> AudioTagging:
    """
    Load a CNN14 AudioTagging model.
    Either checkpoint_path or checkpoint_url must be provided.
    Always resolves to a local path via ensure_checkpoint.
    """
    if not (checkpoint_path or checkpoint_url):
        raise FileNotFoundError("Either checkpoint_path or checkpoint_url must be provided.")

    ckpt = ensure_checkpoint(checkpoint_path, checkpoint_url)  # returns a local path
    return AudioTagging(checkpoint_path=ckpt, device=device)


def run_embedding(at: AudioTagging, wav: np.ndarray) -> np.ndarray:
    try:
        res = at.inference(wav)
    except Exception:
        res = at.inference(wav[None, :])

    emb = None
    if isinstance(res, dict):
        emb = res.get("embedding", None)
    elif isinstance(res, tuple) and len(res) >= 2:
        emb = res[1]
    if emb is None:
        raise RuntimeError("No embedding returned by panns_inference.")
    return _to_numpy(emb).reshape(-1)


def run_cnn14_embedding(model: AudioTagging, wav: np.ndarray) -> np.ndarray:
    """
    Run embedding extraction; validate input waveform.
    Raises ValueError if wav is empty.
    """
    wav = np.asarray(wav)
    if wav.size == 0:
        raise ValueError("waveform must not be empty")
    if wav.dtype != np.float32:
        wav = wav.astype(np.float32, copy=False)
    return run_embedding(model, wav)


def run_cnn14_embeddings_batch(model: AudioTagging, windows: np.ndarray, batch_size: int = 32) -> np.ndarray:
    """
    Compute embeddings for a batch of windows in shape (N, samples).
    Returns array (N, emb_dim) float32.
    """
    if windows.ndim != 2:
        raise ValueError("windows must be 2D (N, samples)")
    n = windows.shape[0]
    embs = []
    i = 0
    while i < n:
        j = min(i + batch_size, n)
        chunk = np.array(windows[i:j], dtype=np.float32, copy=True, order="C")
        # panns_inference supports batched input (N, samples)
        res = model.inference(chunk)
        if isinstance(res, dict):
            emb = res.get("embedding")
        elif isinstance(res, tuple) and len(res) >= 2:
            emb = res[1]
        else:
            raise RuntimeError("Unexpected inference output")
        e = _to_numpy(emb).astype(np.float32, copy=False)
        if e.ndim == 1:
            e = e[None, :]
        embs.append(e)
        i = j
    E = np.concatenate(embs, axis=0).astype(np.float32, copy=False)
    return E
