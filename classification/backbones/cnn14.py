# cnn14.py (suggested changes)
from __future__ import annotations
from typing import Tuple, List, Optional
import numpy as np
from panns_inference import AudioTagging
from core.model_io import _to_numpy, ensure_checkpoint, run_inference

def load_cnn14_model(checkpoint_path: Optional[str] = None, checkpoint_url: Optional[str] = None, device: str = "cpu") -> AudioTagging:
    """
    Load a CNN14 AudioTagging model.
    - Accepts either a local checkpoint_path or a checkpoint_url.
    - device defaults to "cpu".
    """
    if checkpoint_path:
        ckpt = ensure_checkpoint(checkpoint_path, checkpoint_url)
        return AudioTagging(checkpoint_path=ckpt, device=device)
    elif checkpoint_url:
        # If only URL provided, allow AudioTagging to handle it (or pass URL as checkpoint_path)
        # Many wrappers accept a path-like or URL; if not, tests should patch AudioTagging.
        return AudioTagging(checkpoint_path=checkpoint_url, device=device)
    else:
        raise FileNotFoundError("Either checkpoint_path or checkpoint_url must be provided.")

def run_cnn14_inference(model: AudioTagging, wav: np.ndarray) -> Tuple[np.ndarray, List[str]]:
    return run_inference(model, wav)

# def run_cnn14_embedding(model: AudioTagging, wav: np.ndarray) -> np.ndarray:
#     """
#     Run embedding extraction; validate input waveform length.
#     """
#     wav = np.asarray(wav)
#     if wav.size == 0:
#         raise ValueError("waveform must not be empty")
#     return run_embedding(model, wav)

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
    return run_embedding(model, wav)
