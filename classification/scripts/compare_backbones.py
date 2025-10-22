from __future__ import annotations
import argparse
import subprocess
import sys
from typing import List

BACKBONES = ["cnn14", "vggish", "ast", "fusion"]

def main() -> None:
    ap = argparse.ArgumentParser(description="Run classify multiple times with the same params but different backbones.")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--window-sec", type=float, default=2.0)
    ap.add_argument("--hop-sec", type=float, default=0.5)
    ap.add_argument("--pad-last", action="store_true", default=True)
    ap.add_argument("--agg", choices=["mean", "max"], default="mean")
    ap.add_argument("--unknown-threshold", type=float, default=0.25)

    # Optional: head paths per backbone
    ap.add_argument("--head-cnn14", default=None)
    ap.add_argument("--head-vggish", default=None)
    ap.add_argument("--head-ast", default=None)
    ap.add_argument("--head-fusion", default=None)

    # Optional: checkpoints / AST local dir
    ap.add_argument("--checkpoint", default=None)
    ap.add_argument("--checkpoint-url", default=None)
    ap.add_argument("--ast-model-dir", default=None)

    # DB
    ap.add_argument("--write-db", action="store_true", default=False)
    ap.add_argument("--db-url", default=None)
    ap.add_argument("--db-schema", default="audio_cls")

    ap.add_argument("--only", nargs="*", default=None, help="Subset of backbones to run (e.g. --only cnn14 vggish)")
    args = ap.parse_args()

    chosen: List[str] = args.only if args.only else BACKBONES
    for bb in chosen:
        head = {
            "cnn14": args.head_cnn14,
            "vggish": args.head_vggish,
            "ast": args.head_ast,
            "fusion": args.head_fusion,
        }.get(bb)

        cmd = [
            sys.executable, "-m", "classification.scripts.classify",
            "--audio", args.audio,
            "--device", args.device,
            "--window-sec", str(args.window_sec),
            "--hop-sec", str(args.hop_sec),
            "--agg", args.agg,
            "--unknown-threshold", str(args.unknown_threshold),
        ]
        if args.pad_last:
            cmd.append("--pad-last")
        if args.checkpoint:
            cmd += ["--checkpoint", args.checkpoint]
        if args.checkpoint_url:
            cmd += ["--checkpoint-url", args.checkpoint_url]
        if head:
            cmd += ["--head", head]
        if args.ast_model_dir and bb in ("ast", "fusion"):
            cmd += ["--ast-model-dir", args.ast_model_dir]

        # Backbone selection only matters if your classify supports others
        # If your production classify is CNN14-only, use the experimental pipeline instead.
        cmd += ["--backbone", bb]  # no-op if your classify ignores it

        if args.write_db:
            cmd.append("--write-db")
            if args.db_url:
                cmd += ["--db-url", args.db_url]
            if args.db_schema:
                cmd += ["--db-schema", args.db_schema]

        print("\n=== Running:", " ".join(cmd))
        rc = subprocess.call(cmd)
        if rc != 0:
            print(f"[warn] backbone={bb} exited with code {rc}")

if __name__ == "__main__":
    main()
