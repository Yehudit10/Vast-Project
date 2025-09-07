# scripts/classify.py
# Baseline classifier CLI (print-only): loads local file(s), runs PANNs inference, prints Top-K and coarse buckets.

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import List, Optional

from panns_inference import AudioTagging

from core.model_io import (
    SAMPLE_RATE,
    ensure_checkpoint,
    load_audio,
    run_inference,
    load_labels_from_csv,
    summarize_buckets,
)

# Keep a clear, explicit list for discovery speed and user expectations.
SUPPORTED_EXTS = (".wav", ".flac", ".ogg", ".aiff", ".aif", ".au", ".mp3", ".m4a", ".aac", ".opus")


def discover_audio_files(root: pathlib.Path) -> List[pathlib.Path]:
    """Return files under root matching known audio extensions."""
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_EXTS else []
    files: List[pathlib.Path] = []
    for ext in SUPPORTED_EXTS:
        files.extend(root.rglob(f"*{ext}"))
    return sorted(files)


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline CNN14 classifier (print-only).")
    parser.add_argument("--audio", required=True, help="Path to an audio file or a directory with audio files.")
    parser.add_argument(
        "--checkpoint",
        default=str(pathlib.Path.home() / "panns_data" / "Cnn14_mAP=0.431.pth"),
        help="Local path to model weights (default: %(default)s).",
    )
    parser.add_argument(
        "--checkpoint-url",
        default=None,
        help="If local checkpoint is missing, URL to download it using urllib.",
    )
    parser.add_argument(
        "--labels-csv",
        default=None,
        help="Optional path to class_labels_indices.csv to override built-in labels.",
    )
    parser.add_argument("--topk", type=int, default=10, help="How many top labels to print (default: %(default)s).")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu", help="Inference device (default: cpu).")
    args = parser.parse_args()

    root = pathlib.Path(args.audio)

    # Ensure checkpoint exists (or download)
    try:
        ckpt_path = ensure_checkpoint(args.checkpoint, args.checkpoint_url)
    except Exception as e:
        print(f"[error] Unable to prepare checkpoint: {e}")
        sys.exit(1)

    # Create model
    try:
        at = AudioTagging(checkpoint_path=ckpt_path, device=args.device)
    except Exception as e:
        print(f"[error] Failed to load model: {e}")
        sys.exit(2)

    # Discover files
    files = discover_audio_files(root)
    if not files:
        print(f"[warn] No supported audio files found under {root}")
        print(f"[info] Supported extensions: {', '.join(SUPPORTED_EXTS)}")
        sys.exit(0)

    # Optional labels override
    override_labels: Optional[List[str]] = None
    if args.labels_csv:
        override_labels = load_labels_from_csv(args.labels_csv)

    # Process
    for f in files:
        try:
            wav = load_audio(str(f), target_sr=SAMPLE_RATE)
            probs, labels = run_inference(at, wav)

            if override_labels and len(override_labels) == probs.size:
                labels = override_labels

            topk = max(1, int(args.topk))
            idx_sorted = probs.argsort()[::-1][:topk]
            top_pairs = [(labels[i], float(probs[i])) for i in idx_sorted]

            print(f"\n========== {f.name} ==========")
            print("Top predictions:")
            for i, (lab, p) in enumerate(top_pairs, 1):
                print(f" {i:2d}. {lab:40s} {p:7.4f}")

            buckets = summarize_buckets(top_pairs)
            print("\nCoarse buckets (normalized from top-k):")
            for k in ("animal", "vehicle", "shotgun", "other"):
                print(f"- {k:<8} {buckets[k]:7.4f}")

        except Exception as e:
            print(f"[error] Failed on {f}: {e}")


if __name__ == "__main__":
    main()
