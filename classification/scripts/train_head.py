from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import List, Tuple

import joblib
import numpy as np
from dotenv import load_dotenv, find_dotenv
from panns_inference import AudioTagging
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from core.model_io import SAMPLE_RATE, SUPPORTED_EXTS, ensure_checkpoint, load_audio, run_embedding

DEFAULT_CLASSES = ["animal", "vehicle", "shotgun", "other"]
DEFAULT_CKPT = str(pathlib.Path.home() / "panns_data" / "Cnn14_mAP=0.431.pth")


def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def discover_labeled_files(root: pathlib.Path, class_order: List[str]) -> List[Tuple[str, pathlib.Path]]:
    pairs: List[Tuple[str, pathlib.Path]] = []
    for lbl in class_order:
        d = root / lbl
        if not d.exists():
            print(f"[warn] missing class dir: {d}")
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                pairs.append((lbl, p))
    return pairs


def main() -> None:
    load_dotenv(find_dotenv(usecwd=True), override=True)

    ap = argparse.ArgumentParser(description="Train a 4-class head over CNN14 embeddings")

    # environment-driven defaults (for short CLI)
    ap.add_argument("--train-dir", default=os.getenv("TRAIN_DIR"), help="Root dir with subfolders: animal/vehicle/shotgun/other")
    ap.add_argument("--checkpoint", default=os.getenv("CHECKPOINT", DEFAULT_CKPT))
    ap.add_argument("--checkpoint-url", default=os.getenv("CHECKPOINT_URL"))
    ap.add_argument("--device", choices=["cpu", "cuda"], default=os.getenv("DEVICE", "cpu"))
    ap.add_argument("--out", default=os.getenv("HEAD", "models/head.joblib"))
    ap.add_argument("--meta", default=os.getenv("HEAD_META"))

    # algorithmic defaults (fixed in code)
    ap.add_argument("--classes", default=os.getenv("CLASSES", ",".join(DEFAULT_CLASSES)))
    ap.add_argument("--seed", type=int, default=int(os.getenv("SEED", 42)))
    ap.add_argument("--test-size", type=float, default=float(os.getenv("TEST_SIZE", 0.2)))
    ap.add_argument("--debug", action="store_true", default=env_bool("DEBUG", False))

    args = ap.parse_args()

    if not args.train_dir:
        print("[error] --train-dir is required (or set TRAIN_DIR in the environment/.env)")
        sys.exit(2)

    if args.test_size <= 0.0 or args.test_size >= 0.9:
        print(f"[warn] unusual --test-size={args.test_size}; typical values are in [0.1 .. 0.3]")

    out_path = pathlib.Path(args.out)
    meta_path = pathlib.Path(args.meta) if args.meta else out_path.with_suffix(out_path.suffix + ".meta.json")

    if args.debug:
        print("[cfg] train_dir=%r device=%s checkpoint=%r" % (args.train_dir, args.device, args.checkpoint))
        print("[cfg] out=%r meta=%r classes=%r seed=%d test_size=%.3f" %
              (str(out_path), str(meta_path), args.classes, args.seed, args.test_size))

    ckpt = ensure_checkpoint(args.checkpoint, args.checkpoint_url)
    try:
        at = AudioTagging(checkpoint_path=ckpt, device=args.device)
    except Exception as e:
        print(f"[error] failed to load CNN14: {e}")
        sys.exit(3)

    class_order = [x.strip() for x in args.classes.split(",") if x.strip()]
    if not class_order:
        print("[error] parsed empty class_order from --classes")
        sys.exit(4)

    pairs = discover_labeled_files(pathlib.Path(args.train_dir), class_order)
    if not pairs:
        print(f"[error] no labeled files under {args.train_dir}")
        sys.exit(5)

    X, y = [], []
    for lbl, path in pairs:
        try:
            wav = load_audio(str(path), target_sr=SAMPLE_RATE)
            emb = run_embedding(at, wav)
            X.append(emb)
            y.append(class_order.index(lbl))
        except Exception as e:
            print(f"[warn] skipped {path}: {e}")

    if not X:
        print("[error] no embeddings were extracted")
        sys.exit(6)

    X = np.stack(X, axis=0)
    y = np.array(y, dtype=np.int64)
    print(f"[info] dataset: X={X.shape}, y={y.shape} (classes={class_order})")

    unique, counts = np.unique(y, return_counts=True)
    min_count = int(counts.min())
    can_stratify = (unique.size >= 2) and (min_count >= 2)
    if not can_stratify:
        print(f"[warn] cannot stratify: classes={unique.size}, min_count={min_count}. Falling back to random split.")

    rng = int(args.seed)
    np.random.seed(rng)

    Xtr, Xval, ytr, yval = train_test_split(
        X, y,
        test_size=float(args.test_size),
        random_state=rng,
        stratify=(y if can_stratify else None),
    )

    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            max_iter=2000,
            class_weight="balanced",
            multi_class="multinomial",
            solver="saga",
            random_state=rng,
            n_jobs=-1,
        )),
    ])
    pipe.fit(Xtr, ytr)
    acc = pipe.score(Xval, yval)
    print(f"[info] val accuracy: {acc:.3f}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, out_path)

    meta = {
        "class_order": class_order,
        "seed": rng,
        "test_size": float(args.test_size),
        "train_dir": str(pathlib.Path(args.train_dir).resolve()),
        "checkpoint": str(pathlib.Path(args.checkpoint).resolve()),
        "device": args.device,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[info] saved head: {out_path}")
    print(f"[info] saved meta: {meta_path}")


if __name__ == "__main__":
    main()
