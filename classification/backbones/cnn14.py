from __future__ import annotations
from typing import Tuple, List
import numpy as np
from panns_inference import AudioTagging
from core.model_io import ensure_checkpoint, run_inference, run_embedding

def load_cnn14_model(checkpoint_path: str, checkpoint_url: str | None, device: str) -> AudioTagging:
    ckpt = ensure_checkpoint(checkpoint_path, checkpoint_url)
    return AudioTagging(checkpoint_path=ckpt, device=device)

def run_cnn14_inference(model: AudioTagging, wav: np.ndarray) -> Tuple[np.ndarray, List[str]]:
    return run_inference(model, wav)

def run_cnn14_embedding(model: AudioTagging, wav: np.ndarray) -> np.ndarray:
    return run_embedding(model, wav)
