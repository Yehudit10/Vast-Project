from __future__ import annotations
from functools import lru_cache
import numpy as np
import torch
from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
from core.model_io import ensure_numpy_1d

# --- AST (Audio Spectrogram Transformer) ---
try:
    from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
    _HAS_AST = True
except Exception:
    _HAS_AST = False

AST_MODEL_NAME = "MIT/ast-finetuned-audioset-10-10-0.4593"
AST_TARGET_SR = 16000  # AST expects 16kHz

AST_DEFAULT = "MIT/ast-finetuned-audioset-10-10-0.4593"

def _resample_to_target(wav: np.ndarray, sr: int, target_sr: int) -> np.ndarray:
    if sr == target_sr:
        return wav
    try:
        import librosa
        return librosa.resample(wav.astype(np.float32), orig_sr=sr, target_sr=target_sr)
    except Exception:
        # Fallback: very simple linear resample (less accurate than librosa, but works).
        ratio = target_sr / float(sr)
        n_new = max(1, int(round(wav.shape[-1] * ratio)))
        x_old = np.linspace(0.0, 1.0, num=wav.shape[-1], endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_new,       endpoint=False)
        return np.interp(x_new, x_old, wav).astype(np.float32)


@lru_cache(maxsize=1)
def _load_ast_components(model_path: str, device: str):
    """
    Load AST components from a local directory ONLY.
    Requires: model_path directory with config.json + model weights (safetensors or bin).
    Cached via LRU to avoid reloading per window.
    """
    fe = AutoFeatureExtractor.from_pretrained(model_path, local_files_only=True)
    model = AutoModelForAudioClassification.from_pretrained(model_path, local_files_only=True)
    model.to(device)
    model.eval()
    return fe, model


def run_embedding_ast(
    wav: np.ndarray,
    sr: int,
    device: str,
    model_path: Optional[str] = None,
    local_only: bool = True,
    **kwargs,
) -> np.ndarray:
    """
    Compute an embedding from AST by averaging the last hidden state across time.
    Ensures the waveform is resampled to 16 kHz as required by the AST feature extractor.
    Returns a 1D float32 vector (e.g., 768 dims depending on the model).
    """
    if not isinstance(wav, np.ndarray):
        raise AttributeError("Input must be a numpy array")
    # Backward-compat alias: allow ast_model_dir=...
    if (model_path is None) and ("ast_model_dir" in kwargs):
        model_path = kwargs.get("ast_model_dir")
    if not model_path:
        raise RuntimeError("AST model_path (or ast_model_dir) is required for offline inference")

    # Load local components (cached)
    fe, model = _load_ast_components(model_path, device)

    # Ensure numpy float32 1-D
    wav = ensure_numpy_1d(wav)

    # Resample to 16 kHz if needed (AST requires 16k)
    if int(sr) != int(AST_TARGET_SR):
        wav = _resample_to_target(wav, sr=int(sr), target_sr=int(AST_TARGET_SR))
        sr = int(AST_TARGET_SR)

    # Build inputs with the correct sampling_rate
    inputs = fe(wav, sampling_rate=sr, return_tensors="pt")
    for k in inputs:
        inputs[k] = inputs[k].to(model.device)

    with torch.no_grad():
        out = model(**inputs, output_hidden_states=True, return_dict=True)
        last_hs = out.hidden_states[-1]  # (B, T, D)
        emb = last_hs.mean(dim=1).squeeze(0).detach().cpu().numpy().astype(np.float32)  # (D,)
    return emb


def run_ast_embedding(
    wav: np.ndarray,
    sr: int,
    device: str,
    model_path: str,
    local_only: bool = True,
) -> np.ndarray:
    """
    Returns 1-D float32 embedding (e.g., 768 dims).
    """
    return run_embedding_ast(wav, sr=sr, device=device, model_path=model_path, local_only=local_only)
