from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


DEFAULT_BACKBONES = ["cnn14", "vggish", "ast", "fusion"]
DEFAULT_HEADS = ["logreg", "svm", "rf"]


def build_head_path(models_dir: Path, backbone: str, head: str, pattern: str) -> Path:
    """
    Construct a model head path from a pattern, e.g. 'head_{backbone}_{head}.joblib'
    """
    fname = pattern.format(backbone=backbone, head=head)
    return (models_dir / fname).with_suffix(".joblib") if not fname.endswith(".joblib") else models_dir / fname


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run classify.py for multiple backbones and head types with the same params. "
                    "Heads are resolved from a naming pattern in the models dir."
    )
    # Required
    ap.add_argument("--audio", required=True, help="File or directory with audio for inference.")

    # General classify options
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--window-sec", type=float, default=2.0)
    ap.add_argument("--hop-sec", type=float, default=0.5)
    ap.add_argument("--pad-last", action="store_true", default=True)
    ap.add_argument("--agg", choices=["mean", "max"], default="mean")
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--unknown-threshold", type=float, default=0.55)
    ap.add_argument("--checkpoint", default=None, help="CNN14 checkpoint path (used by classify for AudioSet printouts).")
    ap.add_argument("--checkpoint-url", default=None)
    ap.add_argument("--labels-csv", default=None)

    # AST
    ap.add_argument("--ast-model-dir", default=None, help="Local AST model dir (config.json + weights).")

    # DB
    ap.add_argument("--write-db", action="store_true", default=False)
    ap.add_argument("--db-url", default=None)
    ap.add_argument("--db-schema", default="audio_cls")

    # Selection
    ap.add_argument("--backbones", nargs="*", default=DEFAULT_BACKBONES,
                    help=f"Backbones to evaluate (default: {DEFAULT_BACKBONES})")
    ap.add_argument("--heads", nargs="*", default=DEFAULT_HEADS,
                    help=f"Head types to evaluate (default: {DEFAULT_HEADS})")

    # Head discovery
    ap.add_argument("--models-dir", default="models", help="Directory where head .joblib files live.")
    ap.add_argument("--head-pattern", default="head_{backbone}_{head}.joblib",
                    help="Filename pattern to find head files in models-dir. "
                         "Placeholders: {backbone}, {head}")

    # Dry run
    ap.add_argument("--dry-run", action="store_true", help="Print commands without executing.")

    args = ap.parse_args()

    models_dir = Path(args.models_dir)
    if not models_dir.exists():
        print(f"[warn] models-dir not found: {models_dir.resolve()}")

    # Build (backbone, head, head_path) list
    jobs: List[Tuple[str, str, Path]] = []
    for bb in args.backbones:
        for h in args.heads:
            hp = build_head_path(models_dir, bb, h, args.head_pattern)
            if not hp.exists():
                print(f"[warn] head not found, skipping: backbone={bb} head={h} path={hp}")
                continue
            jobs.append((bb, h, hp))

    if not jobs:
        print("[error] no (backbone, head) combinations found. "
              "Check --models-dir and --head-pattern or train heads first.")
        sys.exit(2)

    for (bb, h, hp) in jobs:
        cmd = [
            sys.executable, "-m", "scripts.classify",
            "--audio", args.audio,
            "--device", args.device,
            "--window-sec", str(args.window_sec),
            "--hop-sec", str(args.hop_sec),
            "--agg", args.agg,
            "--topk", str(args.topk),
            "--backbone", bb,
            "--unknown-threshold", str(args.unknown_threshold),
            "--head", str(hp),
        ]
        if args.pad_last:
            cmd.append("--pad-last")
        if args.checkpoint:
            cmd += ["--checkpoint", args.checkpoint]
        if args.checkpoint_url:
            cmd += ["--checkpoint-url", args.checkpoint_url]
        if args.labels_csv:
            cmd += ["--labels-csv", args.labels_csv]
        if args.ast_model_dir and bb == "ast":
            cmd += ["--ast-model-dir", args.ast_model_dir]

        if args.write_db:
            cmd.append("--write-db")
            if args.db_url:
                cmd += ["--db-url", args.db_url]
            if args.db_schema:
                cmd += ["--db-schema", args.db_schema]

        print("\n=== Running:", " ".join(cmd))
        if args.dry_run:
            continue

        rc = subprocess.call(cmd)
        if rc != 0:
            print(f"[warn] classify exited with code {rc}  (backbone={bb}, head={h})")

    print("\n[info] Done.")


if __name__ == "__main__":
    main()
