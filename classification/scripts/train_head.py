from __future__ import annotations

import os
import argparse
import json
import pathlib
import sys
from typing import List, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import joblib
import logging

from dotenv import load_dotenv, find_dotenv
from panns_inference import AudioTagging
from core.model_io import SAMPLE_RATE, SUPPORTED_EXTS, ensure_checkpoint, load_audio, run_embedding

DEFAULT_CLASSES = ["animal", "vehicle", "shotgun", "other"]
LOGGER = logging.getLogger("audio_cls.train_head")


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
            LOGGER.warning("missing class dir: %s", d)
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                pairs.append((lbl, p))
    return pairs


def _setup_logging(debug: bool | None, level: str | None, log_file: str | None) -> None:
    if level:
        try:
            lvl = getattr(logging, level.upper())
        except AttributeError:
            lvl = logging.DEBUG if debug else logging.INFO
    else:
        lvl = logging.DEBUG if debug else logging.INFO

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def main() -> None:
    load_dotenv(find_dotenv(usecwd=True), override=True)

    ap = argparse.ArgumentParser(description="Train a 4-class head over CNN14 embeddings")
    ap.add_argument("--train-dir", default=os.getenv("TRAIN_DIR"))
    ap.add_argument("--checkpoint", default=os.getenv("CHECKPOINT", str(pathlib.Path.home() / "panns_data" / "Cnn14_mAP=0.431.pth")))
    ap.add_argument("--checkpoint-url", default=os.getenv("CHECKPOINT_URL"))
    ap.add_argument("--device", choices=["cpu", "cuda"], default=os.getenv("DEVICE", "cpu"))
    ap.add_argument("--out", default=os.getenv("HEAD", "models/head.joblib"))
    ap.add_argument("--meta", default=os.getenv("HEAD_META"))
    ap.add_argument("--classes", default=os.getenv("CLASSES", ",".join(DEFAULT_CLASSES)))
    ap.add_argument("--seed", type=int, default=int(os.getenv("SEED", 42)))
    ap.add_argument("--test-size", type=float, default=float(os.getenv("TEST_SIZE", 0.2)))
    ap.add_argument("--debug", action="store_true", default=env_bool("DEBUG", False))
    ap.add_argument("--log-level", default=os.getenv("LOG_LEVEL"))
    ap.add_argument("--log-file", default=os.getenv("LOG_FILE"))
    args = ap.parse_args()

    _setup_logging(args.debug, args.log_level, args.log_file)

    if not args.train_dir:
        LOGGER.error("--train-dir is required (or set TRAIN_DIR in .env)")
        sys.exit(2)

    if args.test_size <= 0.0 or args.test_size >= 0.9:
        LOGGER.warning("unusual --test-size=%.3f; typical in [0.1..0.3]", args.test_size)

    out_path = pathlib.Path(args.out)
    meta_path = pathlib.Path(args.meta) if args.meta else pathlib.Path(f"{args.out}.meta.json")

    LOGGER.info("train_dir=%r device=%s checkpoint=%r", args.train_dir, args.device, args.checkpoint)
    LOGGER.info("out=%r meta=%r classes=%r seed=%d test_size=%.3f",
                str(out_path), str(meta_path), args.classes, args.seed, args.test_size)

    ckpt = ensure_checkpoint(args.checkpoint, args.checkpoint_url)

    try:
        if args.device == "cuda":
            try:
                import torch  # type: ignore
                if not torch.cuda.is_available():
                    LOGGER.warning("CUDA requested but not available; falling back to CPU.")
                    args.device = "cpu"
            except Exception:
                LOGGER.warning("Unable to verify CUDA; falling back to CPU.")
                args.device = "cpu"
        at = AudioTagging(checkpoint_path=ckpt, device=args.device)
    except Exception as e:
        LOGGER.exception("failed to load CNN14: %s", e)
        sys.exit(3)

    class_order = [x.strip() for x in args.classes.split(",") if x.strip()]
    if not class_order:
        LOGGER.error("parsed empty class_order from --classes")
        sys.exit(4)

    pairs = discover_labeled_files(pathlib.Path(args.train_dir), class_order)
    if not pairs:
        LOGGER.error("no labeled files under %s", args.train_dir)
        sys.exit(5)

    rng = int(args.seed)
    np.random.seed(rng)

    X, y = [], []
    for lbl, path in pairs:
        try:
            wav = load_audio(str(path), target_sr=SAMPLE_RATE)
            emb = run_embedding(at, wav)
            X.append(emb)
            y.append(class_order.index(lbl))
        except Exception as e:
            LOGGER.warning("skipped %s: %s", path, e)

    if not X:
        LOGGER.error("no embeddings were extracted")
        sys.exit(6)

    X = np.stack(X, axis=0)
    y = np.array(y, dtype=np.int64)
    LOGGER.info("dataset: X=%s, y=%s (classes=%s)", X.shape, y.shape, class_order)

    unique, counts = np.unique(y, return_counts=True)
    min_count = int(counts.min())
    can_stratify = (unique.size >= 2) and (min_count >= 2)
    if not can_stratify:
        LOGGER.warning("cannot stratify: classes=%d, min_count=%d. Falling back to random split.", unique.size, min_count)

    Xtr, Xval, ytr, yval = train_test_split(
        X, y,
        test_size=float(args.test_size),
        random_state=rng,
        stratify=(y if can_stratify else None),
    )

    clf = LogisticRegression(
        max_iter=2000,
        class_weight="balanced",
        multi_class="multinomial",
        solver="saga",
        random_state=rng,
        n_jobs=-1,
    )
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", clf),
    ])

    pipe.fit(Xtr, ytr)
    acc = pipe.score(Xval, yval)
    LOGGER.info("val accuracy: %.3f", acc)

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

    LOGGER.info("saved head: %s", out_path)
    LOGGER.info("saved meta: %s", meta_path)


if __name__ == "__main__":
    main()
