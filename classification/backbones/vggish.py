from __future__ import annotations
import numpy as np
from core.model_io import run_embedding_vggish

def run_vggish_embeddings(
    wav: np.ndarray,
    sr: int,
    window_sec: float,
    hop_sec: float,
    device: str = "cpu",
) -> np.ndarray:
    """
    Returns [num_windows, 128] float32 embeddings.
    """
    return run_embedding_vggish(wav, sr, window_sec, hop_sec, device=device)
