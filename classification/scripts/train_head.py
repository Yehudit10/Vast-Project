# A small logistical head coach over CNN14 ambdings for 4 departments: Animal/vehicle/shotgun/other

from __future__ import annotations
import argparse, json, pathlib, sys
from typing import List, Tuple
import numpy as np

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
import joblib

from panns_inference import AudioTagging
from core.model_io import SAMPLE_RATE, ensure_checkpoint, load_audio, run_embedding

SUPPORTED_EXTS = (".wav", ".flac", ".ogg", ".aiff", ".aif", ".au", ".mp3", ".m4a", ".aac", ".opus")
DEFAULT_CLASSES = ["animal", "vehicle", "shotgun", "other"]

def discover_labeled_files(root: pathlib.Path, class_order: List[str]) -> List[Tuple[str, pathlib.Path]]:
    """
    Expecting structure:
      root/
        animal/*.wav
        vehicle/*.wav
        shotgun/*.wav
        other/*.wav
    returns [(label_name, path), ...]
    """
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

def main():
    ap = argparse.ArgumentParser(description="Train a 4-class head over CNN14 embeddings")
    ap.add_argument("--train-dir", required=True, help="Root dir with subfolders: animal/vehicle/shotgun/other")
    ap.add_argument("--checkpoint", default=str(pathlib.Path.home() / "panns_data" / "Cnn14_mAP=0.431.pth"))
    ap.add_argument("--checkpoint-url", default=None)
    ap.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    ap.add_argument("--out", default="models/head.joblib", help="Output path for trained head (joblib)")
    ap.add_argument("--meta", default=None, help="Optional path for meta json (default: <out>.meta.json)")
    ap.add_argument("--classes", default=",".join(DEFAULT_CLASSES),
                    help=f"Class order (comma-separated). Default: {','.join(DEFAULT_CLASSES)}")
    args = ap.parse_args()

    class_order = [x.strip() for x in args.classes.split(",") if x.strip()]
    out_path = pathlib.Path(args.out)
    meta_path = pathlib.Path(args.meta) if args.meta else out_path.with_suffix(out_path.suffix + ".meta.json")

    ckpt = ensure_checkpoint(args.checkpoint, args.checkpoint_url)
    try:
        at = AudioTagging(checkpoint_path=ckpt, device=args.device)
    except Exception as e:
        print(f"[error] failed to load CNN14: {e}")
        sys.exit(2)

    pairs = discover_labeled_files(pathlib.Path(args.train_dir), class_order)
    if not pairs:
        print(f"[error] no labeled files found under {args.train_dir}")
        sys.exit(3)

    X, y = [], []
    for lbl, path in pairs:
        try:
            wav = load_audio(str(path), target_sr=SAMPLE_RATE)
            emb = run_embedding(at, wav)  # (D,)
            X.append(emb)
            y.append(class_order.index(lbl))
        except Exception as e:
            print(f"[warn] skipped {path}: {e}")

    if not X:
        print("[error] no embeddings were extracted")
        sys.exit(4)

    X = np.stack(X, axis=0)
    y = np.array(y, dtype=np.int64)
    print(f"[info] dataset: X={X.shape}, y={y.shape} (classes={class_order})")

    Xtr, Xval, ytr, yval = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", multi_class="auto", solver="saga")),
    ])
    pipe.fit(Xtr, ytr)
    acc = pipe.score(Xval, yval)
    print(f"[info] val accuracy: {acc:.3f}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, out_path)
    meta = {"class_order": class_order}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f".[info] saved head: {out_path}")
    print(f"[info] saved meta: {meta_path}")

if __name__ == "__main__":
    main()
