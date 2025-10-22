from __future__ import annotations
from typing import List
import numpy as np
from core.model_io import ensure_numpy_1d
import torch

try:
    from torchvggish import vggish, vggish_input
    _HAS_VGGISH = True
except Exception:
    _HAS_VGGISH = False


def _vggish_embed_window(wav: np.ndarray, sr: int, device: str) -> np.ndarray:
    """
    Embed a single waveform window with VGGish and return a single 128-D vector.
    Aggregates multiple 0.96s patches by mean.
    """
    # Force numpy float32 1-D input
    wav = ensure_numpy_1d(wav)

    if not _HAS_VGGISH:
        raise RuntimeError("torchvggish is not installed. Run: pip install torchvggish==0.2 soundfile")

    # Build VGGish examples – may return numpy or torch tensor, 3D [N,96,64] or 4D [N,1,96,64]
    ex = vggish_input.waveform_to_examples(wav.astype(np.float32, copy=False), sr)

    # Normalize to numpy float32
    if not isinstance(ex, np.ndarray):
        if hasattr(ex, "detach") and hasattr(ex, "cpu") and hasattr(ex, "numpy"):
            try:
                ex = ex.detach().cpu().numpy()
            except Exception:
                ex = np.asarray(ex)
        elif hasattr(ex, "numpy") and callable(getattr(ex, "numpy", None)):
            try:
                ex = ex.numpy()
            except Exception:
                ex = np.asarray(ex)
        else:
            ex = np.asarray(ex)
    ex = ex.astype(np.float32, copy=False)

    if ex.size == 0:
        return np.zeros(128, dtype=np.float32)

    # Ensure 4D [N, 1, 96, 64] for conv2d:
    # - if [N,96,64]  → add channel dim
    # - if [N,1,96,64] → keep as-is
    if ex.ndim == 3:
        x_np = ex[:, None, :, :]           # [N,1,96,64]
    elif ex.ndim == 4:
        x_np = ex                          # already [N,1,96,64]
    else:
        ex = np.squeeze(ex)
        if ex.ndim == 3:
            x_np = ex[:, None, :, :]
        else:
            raise RuntimeError(f"Unexpected VGGish input shape: {ex.shape}")

    dev = torch.device(device)
    model = vggish().to(dev).eval()
    with torch.inference_mode():
        x = torch.from_numpy(x_np).to(dev)   # [N,1,96,64]
        feats = model(x)                     # [N,128]
        emb = feats.mean(dim=0).detach().cpu().numpy().astype(np.float32)

    return emb


def run_embedding_vggish(
    waveform: np.ndarray,
    sr: int,
    window_sec: float,
    hop_sec: float,
    device: str = "cpu",
) -> np.ndarray:
    """
    Slice waveform into windows and embed each with VGGish.
    Always returns float32 array of shape [num_windows, 128].
    """
    waveform = ensure_numpy_1d(waveform)

    win_len = int(round(window_sec * sr))
    hop_len = int(round(hop_sec * sr))

    # If clip shorter than one window → embed whole clip once
    if win_len <= 0 or hop_len <= 0 or waveform.size < win_len:
        e = _vggish_embed_window(waveform, sr, device=device)
        e = np.asarray(e, dtype=np.float32).reshape(-1)
        if e.size != 128:
            e = np.zeros(128, dtype=np.float32)
        return e[None, :]  # [1, 128]

    embs: List[np.ndarray] = []
    start = 0
    end = win_len
    while end <= waveform.size:
        chunk = waveform[start:end]
        e = _vggish_embed_window(chunk, sr, device=device)
        e = np.asarray(e, dtype=np.float32).reshape(-1)
        if e.size != 128:
            # guard: enforce 128-D per window
            e = np.zeros(128, dtype=np.float32)
        embs.append(e)
        start += hop_len
        end = start + win_len

    if not embs:
        e = _vggish_embed_window(waveform, sr, device=device)
        e = np.asarray(e, dtype=np.float32).reshape(-1)
        if e.size != 128:
            e = np.zeros(128, dtype=np.float32)
        embs.append(e)

    # Always return 2D [num_windows, 128]
    return np.vstack(embs).astype(np.float32, copy=False)


def run_vggish_embeddings(
    wav: np.ndarray,
    sr: int,
    window_sec: float = 2.0,
    hop_sec: float = 1.0,
    device: str = "cpu",
) -> np.ndarray:
    """
    Returns [num_windows, 128] float32 embeddings.
    """
    return run_embedding_vggish(wav, sr, window_sec, hop_sec, device=device)
