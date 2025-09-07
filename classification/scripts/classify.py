# scripts/classify.py
# Baseline classifier CLI: runs PANNs inference on windows and prints:
# - File-level Top-K (AudioSet) using aggregated clipwise probabilities
# - File-level coarse buckets (animal/vehicle/shotgun/other) averaged over windows
# - Optional: file-level 4-class probabilities from a trained head (LogReg over embeddings)
# - Optional: per-window previews

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
    summarize_buckets,
)

# Explicit extension list keeps discovery predictable cross-platform
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
    parser = argparse.ArgumentParser(description="Baseline CNN14 classifier with windowing & aggregation.")
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

    # Windowing & aggregation
    parser.add_argument("--window-sec", type=float, default=2.0, help="Window length in seconds (default: 2.0).")
    parser.add_argument("--hop-sec", type=float, default=0.5, help="Hop between windows in seconds (default: 0.5).")
    parser.add_argument("--pad-last", action="store_true", help="Pad the last partial window to full size if needed.")
    parser.add_argument("--agg", choices=["mean", "max"], default="mean",
                        help="Aggregation over windows for file-level output (default: mean).")
    parser.add_argument("--print-windows", action="store_true",
                        help="Print a short per-window preview (top-3).")

    # Optional trained head (LogReg over embeddings)
    parser.add_argument("--head", default=None, help="Optional path to a trained 4-class head (joblib).")

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

    # Optional: load trained 4-class head
    head = None
    head_meta = {"class_order": ["animal", "vehicle", "shotgun", "other"]}
    if args.head:
        try:
            import joblib, json
            head = joblib.load(args.head)
            meta_path = pathlib.Path(args.head).with_suffix(pathlib.Path(args.head).suffix + ".meta.json")
            if meta_path.exists():
                head_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            print(f"[info] loaded head: {args.head} (classes={head_meta['class_order']})")
        except Exception as e:
            print(f"[warn] failed to load head '{args.head}': {e}")
            head = None

    # Discover files
    files = discover_audio_files(root)
    if not files:
        print(f"[warn] No supported audio files found under {root}")
        print(f"[info] Supported extensions: {', '.join(SUPPORTED_EXTS)}")
        sys.exit(0)

    # Optional labels override (explicit CSV)
    override_labels: Optional[List[str]] = None
    if args.labels_csv:
        from core.model_io import load_labels_from_csv
        override_labels = load_labels_from_csv(args.labels_csv)

    # Process files
    for f in files:
        try:
            from core.model_io import segment_waveform, aggregate_matrix
            import numpy as _np

            wav = load_audio(str(f), target_sr=SAMPLE_RATE)

            # Windowing
            windows = segment_waveform(
                wav,
                sr=SAMPLE_RATE,
                window_sec=float(args.window_sec),
                hop_sec=float(args.hop_sec),
                pad_last=bool(args.pad_last),
            )
            if not windows:
                print(f"[warn] No windows produced for {f.name}")
                continue

            # Per-window predictions (AudioSet clipwise)
            win_probs_list: List[_np.ndarray] = []
            per_window_labels: Optional[List[str]] = None

            # Optional head (4-class)
            head_probs_list: List[_np.ndarray] = []

            for (t0, t1, seg) in windows:
                probs, labs = run_inference(at, seg)
                if per_window_labels is None:
                    per_window_labels = labs
                    if override_labels and len(override_labels) == probs.size:
                        per_window_labels = override_labels
                win_probs_list.append(probs)

                if head is not None:
                    try:
                        from core.model_io import run_embedding
                        emb = run_embedding(at, seg).reshape(1, -1)
                        hp = head.predict_proba(emb)[0]
                        head_probs_list.append(hp)
                    except Exception as e:
                        print(f"[warn] head inference failed on window {t0:.2f}-{t1:.2f}: {e}")

            if per_window_labels is None:
                print(f"[error] No labels available for {f.name}")
                continue

            # Aggregate to file-level
            probs_mat = _np.stack(win_probs_list, axis=0)               # (num_windows, C)
            agg_clipwise = aggregate_matrix(probs_mat, mode=args.agg)   # (C,)

            # File-level Top-K from aggregated clipwise
            topk = max(1, int(args.topk))
            idx_sorted_file = agg_clipwise.argsort()[::-1][:topk]
            top_pairs_file = [(per_window_labels[i], float(agg_clipwise[i])) for i in idx_sorted_file]

            # Bucket averaging over windows (more stable than a single Top-K bucket)
            from core.model_io import summarize_buckets as _summ
            buckets_seq = []
            for probs in win_probs_list:
                idx_sorted = probs.argsort()[::-1][:topk]
                top_pairs = [(per_window_labels[i], float(probs[i])) for i in idx_sorted]
                buckets_seq.append(_summ(top_pairs))
            bucket_keys = ("animal", "vehicle", "shotgun", "other")
            buckets_mean = {k: float(_np.mean([b[k] for b in buckets_seq])) for k in bucket_keys}

            # Print file-level results
            print(f"\n========== {f.name} ==========")
            print(f"Windows: {len(windows)}  (window={args.window_sec:.2f}s, hop={args.hop_sec:.2f}s, agg={args.agg})")

            print("\nFile-level Top predictions (aggregated):")
            for i, (lab, p) in enumerate(top_pairs_file, 1):
                print(f" {i:2d}. {lab:40s} {p:7.4f}")

            print("\nFile-level coarse buckets (mean over windows):")
            for k in bucket_keys:
                print(f"- {k:<8} {buckets_mean[k]:7.4f}")

            # Optional: aggregated head (4-class)
            if head is not None and len(head_probs_list) > 0:
                H = _np.stack(head_probs_list, axis=0)           # (num_windows, 4)
                agg_head = aggregate_matrix(H, mode=args.agg)    # (4,)
                class_order = head_meta.get("class_order", ["animal", "vehicle", "shotgun", "other"])
                print("\nFile-level Head (4-class) probabilities (aggregated):")
                for cls, p in zip(class_order, agg_head):
                    print(f"- {cls:<8} {float(p):7.4f}")

            # Optional: per-window preview
            if args.print_windows:
                print("\nPer-window preview (AudioSet top-3):")
                for (t0, t1, _seg), probs in zip(windows, win_probs_list):
                    idx_sorted = probs.argsort()[::-1][:min(topk, 3)]
                    short_pairs = [(per_window_labels[i], float(probs[i])) for i in idx_sorted]
                    print(f"  [{t0:6.2f}s - {t1:6.2f}s]  " +
                          " | ".join(f"{lab}={p:0.3f}" for lab, p in short_pairs))

                if head is not None and len(head_probs_list) > 0:
                    class_order = head_meta.get("class_order", ["animal", "vehicle", "shotgun", "other"])
                    print("\nPer-window Head (4-class) preview:")
                    for (t0, t1, _seg), hp in zip(windows, head_probs_list):
                        row = " ".join(f"{cls}={float(p):0.3f}" for cls, p in zip(class_order, hp))
                        print(f"  [{t0:6.2f}s - {t1:6.2f}s]  {row}")

        except Exception as e:
            print(f"[error] Failed on {f}: {e}")


if __name__ == "__main__":
    main()
