from __future__ import annotations
import numpy as np
from core.model_io import run_embedding_ast

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
