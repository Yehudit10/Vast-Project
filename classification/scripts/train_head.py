# English only.
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
from sklearn.model_selection import train_test_split

from head import build_head_pipeline
from backbones.cnn14 import load_cnn14_model, run_cnn14_embedding
from backbones.vggish import run_vggish_embeddings
from backbones.ast import run_ast_embedding
from core.model_io import SAMPLE_RATE, SUPPORTED_EXTS, load_audio, ensure_numpy_1d

DEFAULT_CLASSES = [
    "predatory_animals",
    "non_predatory_animals",
    "birds",
    "fire",
    "footsteps",
    "insects",
    "screaming",
    "shotgun",
    "stormy_weather",
    "streaming_water",
    "vehicle",
]

DEFAULT_CKPT = str(pathlib.Path.home() / "panns_data" / "Cnn14_mAP=0.431.pth")

def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

def discover_labeled_files(root: pathlib.Path, class_order: List[str]) -> List[Tuple[pathlib.Path, str]]:
    pairs: List[Tuple[pathlib.Path, str]] = []
    for lbl in class_order:
        class_dir = root / lbl
        if not class_dir.exists():
            print(f"[warn] missing class dir: {class_dir}")
            continue
        for file_path in class_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTS:
                pairs.append((file_path, lbl))
    return pairs


def _embed_clip(backbone: str, at: AudioTagging | None, wav: np.ndarray, device: str, ast_model_dir: str | None) -> np.ndarray:
    if backbone == "vggish":
        clip_sec = float(len(wav) / SAMPLE_RATE)
        e = run_vggish_embeddings(wav, SAMPLE_RATE, window_sec=clip_sec, hop_sec=clip_sec, device=device)[0]
        return e.astype(np.float32, copy=False)
    if backbone == "ast":
        if not ast_model_dir:
            raise RuntimeError("AST requires --ast-model-dir")
        return run_ast_embedding(wav, sr=SAMPLE_RATE, device=device, model_path=ast_model_dir)
    if backbone == "fusion":
        assert at is not None
        e_c = run_cnn14_embedding(at, wav).astype(np.float32, copy=False)
        clip_sec = float(len(wav) / SAMPLE_RATE)
        e_v = run_vggish_embeddings(wav, SAMPLE_RATE, window_sec=clip_sec, hop_sec=clip_sec, device=device)[0].astype(np.float32, copy=False)
        return np.concatenate([e_c, e_v], axis=0).astype(np.float32, copy=False)
    assert at is not None
    return run_cnn14_embedding(at, wav).astype(np.float32, copy=False)

def main() -> None:
    load_dotenv(find_dotenv(usecwd=True), override=True)

    ap = argparse.ArgumentParser(description="Train a multi-class head over embeddings (cnn14 / vggish / fusion / ast).")
    ap.add_argument("--train-dir", default=os.getenv("TRAIN_DIR"),
                    help="Root dir with one subfolder per class (e.g., predatory_animals/...).")
    ap.add_argument("--checkpoint", default=os.getenv("CHECKPOINT", DEFAULT_CKPT))
    ap.add_argument("--checkpoint-url", default=os.getenv("CHECKPOINT_URL"))
    ap.add_argument("--device", choices=["cpu", "cuda"], default=os.getenv("DEVICE", "cpu"))
    ap.add_argument("--out", default=os.getenv("HEAD", "models/head.joblib"))
    ap.add_argument("--meta", default=os.getenv("HEAD_META"))

    ap.add_argument("--classes", default=os.getenv("CLASSES", ",".join(DEFAULT_CLASSES)))
    ap.add_argument("--seed", type=int, default=int(os.getenv("SEED", 42)))
    ap.add_argument("--test-size", type=float, default=float(os.getenv("TEST_SIZE", 0.2)))
    ap.add_argument("--debug", action="store_true", default=env_bool("DEBUG", False))
    ap.add_argument("--backbone", type=str, default="cnn14", choices=["cnn14", "vggish", "fusion", "ast"])
    ap.add_argument("--ast-model-dir", default=os.getenv("AST_MODEL_DIR"), help="AST model directory (offline).")

    # NEW: head type selection
    ap.add_argument("--head-type", type=str, default=os.getenv("HEAD_TYPE", "logreg"),
                    choices=["logreg", "svm", "rf"],
                    help="Classifier head to train over embeddings.")

    args = ap.parse_args()

    if not args.train_dir:
        print("[error] --train-dir is required (or set TRAIN_DIR in the environment/.env)")
        sys.exit(2)

    if args.test_size <= 0.0 or args.test_size >= 0.9:
        print(f"[warn] unusual --test-size={args.test_size}; typical values are in [0.1 .. 0.3]")

    if args.backbone == "ast" and not args.ast_model_dir:
        print("[error] backbone=ast requires --ast-model-dir (offline AST model directory)")
        sys.exit(7)

    out_path = pathlib.Path(args.out)
    meta_path = pathlib.Path(args.meta) if args.meta else out_path.with_suffix(out_path.suffix + ".meta.json")

    at = None
    if args.backbone in ("cnn14", "fusion"):
        at = load_cnn14_model(args.checkpoint, args.checkpoint_url, device=args.device)

    class_order = [x.strip() for x in args.classes.split(",") if x.strip()]
    if not class_order:
        print("[error] parsed empty class_order from --classes")
        sys.exit(4)

    pairs = discover_labeled_files(pathlib.Path(args.train_dir), class_order)
    if not pairs:
        print(f"[error] no labeled files under {args.train_dir}")
        sys.exit(5)

    X, y = [], []
    for path, lbl in pairs:
        try:
            wav = load_audio(str(path), target_sr=SAMPLE_RATE)
            wav = ensure_numpy_1d(wav)
            emb = _embed_clip(args.backbone, at, wav, args.device, args.ast_model_dir)
            X.append(emb)
            y.append(class_order.index(lbl))
        except Exception as e:
            import traceback
            print(f"[warn] skipped {path}: {e} ({type(e).__name__})")
            traceback.print_exc()

    if not X:
        print("[error] no embeddings were extracted")
        sys.exit(6)

    X = np.stack(X, axis=0).astype(np.float32, copy=False)
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

    pipe = build_head_pipeline(head_type=args.head_type, seed=rng)
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
        "checkpoint": (str(pathlib.Path(args.checkpoint).resolve()) if args.backbone in ("cnn14", "fusion") else ""),
        "device": args.device,
        "backbone": args.backbone,
        "embedding_dim": int(X.shape[1]),
        "head_type": str(args.head_type),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[info] saved head: {out_path}")
    print(f"[info] saved meta: {meta_path}")

if __name__ == "__main__":  # pragma: no cover
    main()


# # English only.
# from classification.pipeline.train_head import main

# if __name__ == "__main__":  # pragma: no cover
#     main()


# # from __future__ import annotations

# # import argparse
# # import json
# # import os
# # import pathlib
# # import sys
# # from typing import List, Tuple

# # import joblib
# # import numpy as np
# # from dotenv import load_dotenv, find_dotenv
# # from panns_inference import AudioTagging
# # from sklearn.linear_model import LogisticRegression
# # from sklearn.model_selection import train_test_split
# # from sklearn.pipeline import Pipeline
# # from sklearn.preprocessing import StandardScaler

# # from core.model_io import SAMPLE_RATE, SUPPORTED_EXTS, ensure_checkpoint, load_audio, run_embedding, run_embedding_vggish, ensure_numpy_1d, run_embedding_ast


# # DEFAULT_CLASSES = ["animal", "vehicle", "shotgun", "other"]
# # DEFAULT_CKPT = str(pathlib.Path.home() / "panns_data" / "Cnn14_mAP=0.431.pth")


# # def env_bool(name: str, default: bool = False) -> bool:
# #     v = os.getenv(name)
# #     if v is None:
# #         return default
# #     return v.strip().lower() in ("1", "true", "yes", "on")


# # def discover_labeled_files(root: pathlib.Path, class_order: List[str]) -> List[Tuple[str, pathlib.Path]]:
# #     pairs: List[Tuple[str, pathlib.Path]] = []
# #     for lbl in class_order:
# #         d = root / lbl
# #         if not d.exists():
# #             print(f"[warn] missing class dir: {d}")
# #             continue
# #         for p in d.rglob("*"):
# #             if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
# #                 pairs.append((lbl, p))
# #     return pairs


# # def main() -> None:
# #     load_dotenv(find_dotenv(usecwd=True), override=True)

# #     ap = argparse.ArgumentParser(description="Train a 4-class head over audio embeddings (cnn14 / vggish / fusion)")

# #     # environment-driven defaults (for short CLI)
# #     ap.add_argument("--train-dir", default=os.getenv("TRAIN_DIR"), help="Root dir with subfolders: animal/vehicle/shotgun/other")
# #     ap.add_argument("--checkpoint", default=os.getenv("CHECKPOINT", DEFAULT_CKPT))
# #     ap.add_argument("--checkpoint-url", default=os.getenv("CHECKPOINT_URL"))
# #     ap.add_argument("--device", choices=["cpu", "cuda"], default=os.getenv("DEVICE", "cpu"))
# #     ap.add_argument("--out", default=os.getenv("HEAD", "models/head.joblib"))
# #     ap.add_argument("--meta", default=os.getenv("HEAD_META"))

# #     # algorithmic defaults (fixed in code)
# #     ap.add_argument("--classes", default=os.getenv("CLASSES", ",".join(DEFAULT_CLASSES)))
# #     ap.add_argument("--seed", type=int, default=int(os.getenv("SEED", 42)))
# #     ap.add_argument("--test-size", type=float, default=float(os.getenv("TEST_SIZE", 0.2)))
# #     ap.add_argument("--debug", action="store_true", default=env_bool("DEBUG", False))
# #     ap.add_argument(
# #         "--backbone",
# #         type=str,
# #         default="cnn14",
# #         choices=["cnn14", "vggish", "fusion", "ast"],
# #         help="Which pretrained backbone to use for embeddings."
# #     )
# #     ap.add_argument("--ast-model-dir", default=os.getenv("AST_MODEL_DIR"),
# #                 help="Local folder of AST model (config.json + weights). If set, runs offline.")

# #     args = ap.parse_args()

# #     if not args.train_dir:
# #         print("[error] --train-dir is required (or set TRAIN_DIR in the environment/.env)")
# #         sys.exit(2)

# #     if args.test_size <= 0.0 or args.test_size >= 0.9:
# #         print(f"[warn] unusual --test-size={args.test_size}; typical values are in [0.1 .. 0.3]")

# #     out_path = pathlib.Path(args.out)
# #     meta_path = pathlib.Path(args.meta) if args.meta else out_path.with_suffix(out_path.suffix + ".meta.json")

# #     if args.debug:
# #         print("[cfg] train_dir=%r device=%s checkpoint=%r" % (args.train_dir, args.device, args.checkpoint))
# #         print("[cfg] out=%r meta=%r classes=%r seed=%d test_size=%.3f" %
# #               (str(out_path), str(meta_path), args.classes, args.seed, args.test_size))
    
# #     if args.backbone == "ast" and not args.ast_model_dir:
# #         print("[error] backbone=ast requires --ast-model-dir (offline AST model directory)")
# #         sys.exit(7)
        
# #     # Load backbones
# #     at = None
# #     if args.backbone in ("cnn14", "fusion"):
# #         ckpt = ensure_checkpoint(args.checkpoint, args.checkpoint_url)
# #         try:
# #             at = AudioTagging(checkpoint_path=ckpt, device=args.device)
# #         except Exception as e:
# #             print(f"[error] failed to load CNN14: {e}")
# #             sys.exit(3)

# #     class_order = [x.strip() for x in args.classes.split(",") if x.strip()]
# #     if not class_order:
# #         print("[error] parsed empty class_order from --classes")
# #         sys.exit(4)

# #     pairs = discover_labeled_files(pathlib.Path(args.train_dir), class_order)
# #     if not pairs:
# #         print(f"[error] no labeled files under {args.train_dir}")
# #         sys.exit(5)

# #     X, y = [], []
# #     for lbl, path in pairs:
# #         try:
# #             # Load and normalize audio to numpy float32 1-D
            
# #             wav = load_audio(str(path), target_sr=SAMPLE_RATE)
# #             wav = ensure_numpy_1d(wav)

# #             if args.backbone == "vggish":
# #                 clip_sec = float(len(wav) / SAMPLE_RATE)
# #                 emb_mat = run_embedding_vggish(
# #                     wav, SAMPLE_RATE,
# #                     window_sec=clip_sec, hop_sec=clip_sec,
# #                     device=args.device
# #                 )  # [1, 128]
# #                 emb = emb_mat[0].astype(np.float32, copy=False)

# #             elif args.backbone == "ast":
# #                 emb = run_embedding_ast(
# #                     wav, sr=SAMPLE_RATE, device=args.device, model_path=args.ast_model_dir
# #                 )  # e.g., (768,)
                
# #             elif args.backbone == "fusion":
# #                 # existing fusion path (CNN14 + VGGish)
# #                 emb_cnn14 = run_embedding(at, wav).astype(np.float32, copy=False)
# #                 clip_sec = float(len(wav) / SAMPLE_RATE)
# #                 emb_vgg = run_embedding_vggish(
# #                     wav, SAMPLE_RATE,
# #                     window_sec=clip_sec, hop_sec=clip_sec,
# #                     device=args.device
# #                 )[0].astype(np.float32, copy=False)
# #                 emb = np.concatenate([emb_cnn14, emb_vgg], axis=0).astype(np.float32, copy=False)

# #             else:  # cnn14
# #                 emb = run_embedding(at, wav).astype(np.float32, copy=False)

            
# #             # Guard for VGGish dimensionality
# #             if args.backbone == "vggish" and emb.shape != (128,):
# #                 print(f"[warn] skipped {path}: VGGish embedding not 128-D (got {emb.shape})")
# #                 continue
            

# #             X.append(emb)
# #             y.append(class_order.index(lbl))
       


# #         except Exception as e:
# #             import traceback
# #             print(f"[warn] skipped {path}: {e} ({type(e).__name__})")
# #             traceback.print_exc()
# #             try:
# #                 print(f"[dbg] last wav type={type(wav)} dtype={getattr(wav,'dtype',None)} shape={getattr(wav,'shape',None)}")
# #             except Exception:
# #                 pass

# #     if not X:
# #         print("[error] no embeddings were extracted")
# #         sys.exit(6)

# #     X = np.stack(X, axis=0)
# #     y = np.array(y, dtype=np.int64)
# #     print(f"[info] dataset: X={X.shape}, y={y.shape} (classes={class_order})")

# #     unique, counts = np.unique(y, return_counts=True)
# #     min_count = int(counts.min())
# #     can_stratify = (unique.size >= 2) and (min_count >= 2)
# #     if not can_stratify:
# #         print(f"[warn] cannot stratify: classes={unique.size}, min_count={min_count}. Falling back to random split.")

# #     rng = int(args.seed)
# #     np.random.seed(rng)

# #     Xtr, Xval, ytr, yval = train_test_split(
# #         X, y,
# #         test_size=float(args.test_size),
# #         random_state=rng,
# #         stratify=(y if can_stratify else None),
# #     )

# #     pipe = Pipeline([
# #         ("scaler", StandardScaler()),
# #         ("clf", LogisticRegression(
# #             max_iter=2000,
# #             class_weight="balanced",
# #             multi_class="multinomial",
# #             solver="saga",
# #             random_state=rng,
# #             n_jobs=-1,
# #         )),
# #     ])
# #     pipe.fit(Xtr, ytr)
# #     acc = pipe.score(Xval, yval)
# #     print(f"[info] val accuracy: {acc:.3f}")

# #     out_path.parent.mkdir(parents=True, exist_ok=True)
# #     joblib.dump(pipe, out_path)

# #     meta = {
# #         "class_order": class_order,
# #         "seed": rng,
# #         "test_size": float(args.test_size),
# #         "train_dir": str(pathlib.Path(args.train_dir).resolve()),
# #         "checkpoint": (str(pathlib.Path(args.checkpoint).resolve()) if args.backbone in ("cnn14", "fusion") else ""),
# #         "device": args.device,
# #         "backbone": args.backbone,
# #         "embedding_dim": int(X.shape[1]),
# #     }


# #     meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

# #     print(f"[info] saved head: {out_path}")
# #     print(f"[info] saved meta: {meta_path}")


# # if __name__ == "__main__":  # pragma: no cover
# #     main()
