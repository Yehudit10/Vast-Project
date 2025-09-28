from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import uuid
from typing import List, Optional

import logging
import numpy as np
from dotenv import load_dotenv, find_dotenv
from panns_inference import AudioTagging

from classification.backbones.cnn14 import load_cnn14_model, run_cnn14_embedding
from classification.backbones.vggish import run_vggish_embeddings
from classification.backbones.ast import run_ast_embedding
from core.model_io import (
    SAMPLE_RATE,
    SUPPORTED_EXTS,
    load_audio,
    run_inference_with_embedding,
    segment_waveform,
    aggregate_matrix,
    load_labels_from_csv,
)

LOGGER = logging.getLogger("audio_cls.classify")
DEFAULT_CKPT = str(pathlib.Path.home() / "panns_data" / "Cnn14_mAP=0.431.pth")

def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

def discover_audio_files(root: pathlib.Path) -> List[pathlib.Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_EXTS else []
    files: List[pathlib.Path] = []
    for ext in SUPPORTED_EXTS:
        files.extend(root.rglob(f"*{ext}"))
    return sorted(files)

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

def softmax_1d(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    if x.size == 0:
        return x
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    m = float(np.max(x))
    y = np.exp(x - m)
    s = float(np.sum(y))
    if not np.isfinite(s) or s <= 0.0:
        return np.full_like(x, 1.0 / x.size)
    return y / s

def main() -> None:
    dotenv_path = find_dotenv(usecwd=True)
    load_dotenv(dotenv_path=dotenv_path, override=True)

    ap = argparse.ArgumentParser(description="Windowed inference + aggregation with optional unknown fallback.")
    ap.add_argument("--audio", required=True, help="Path to an audio file or a directory.")

    # environment-driven defaults
    ap.add_argument("--checkpoint", default=os.getenv("CHECKPOINT", DEFAULT_CKPT))
    ap.add_argument("--checkpoint-url", default=os.getenv("CHECKPOINT_URL"))
    ap.add_argument("--device", choices=["cpu", "cuda"], default=os.getenv("DEVICE", "cpu"))
    ap.add_argument("--labels-csv", default=os.getenv("LABELS_CSV"))
    ap.add_argument("--head", default=os.getenv("HEAD"))

    # algorithmic defaults
    ap.add_argument("--window-sec", type=float, default=2.0)
    ap.add_argument("--hop-sec", type=float, default=0.5)
    ap.add_argument("--pad-last", dest="pad_last", action="store_true", default=False)
    ap.add_argument("--no-pad-last", dest="pad_last", action="store_false")
    ap.add_argument("--agg", choices=["mean", "max"], default="mean")
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--print-windows", action="store_true", default=env_bool("PRINT_WINDOWS", False))

    # Unknown fallback
    ap.add_argument("--unknown-threshold", type=float, default=float(os.getenv("UNKNOWN_THRESHOLD", 0.55)),
                    help="If top-1 aggregated probability < threshold, final label is 'another'.")

    # DB options
    ap.add_argument("--write-db", action="store_true", default=env_bool("WRITE_DB", False))
    ap.add_argument("--db-url", default=os.getenv("DB_URL"))
    ap.add_argument("--db-schema", default=os.getenv("DB_SCHEMA", "audio_cls"))
    ap.add_argument("--notes", default=None, help="Optional notes for the run metadata")

    # logging
    ap.add_argument("--debug", action="store_true", default=env_bool("DEBUG", False))
    ap.add_argument("--log-level", default=os.getenv("LOG_LEVEL"))
    ap.add_argument("--log-file", default=os.getenv("LOG_FILE"))

    # backbone choice
    ap.add_argument("--backbone", type=str, default="cnn14", choices=["cnn14", "vggish", "fusion", "ast"])
    ap.add_argument("--ast-model-dir", default=os.getenv("AST_MODEL_DIR"), help="Path to a local AST model dir.")
    ap.add_argument("--hf-offline", action="store_true", default=env_bool("HF_OFFLINE", False))

    args = ap.parse_args()
    if args.hf_offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    if args.backbone == "ast" and not args.ast_model_dir:
        LOGGER.error("backbone=ast requires --ast-model-dir in this network environment")
        sys.exit(5)

    _setup_logging(args.debug, args.log_level, args.log_file)

    if args.window_sec <= 0:
        LOGGER.error("--window-sec must be > 0"); sys.exit(2)
    if args.hop_sec <= 0:
        LOGGER.error("--hop-sec must be > 0"); sys.exit(2)
    if args.hop_sec > args.window_sec:
        LOGGER.warning("hop-sec > window-sec; sliding will skip windows. Consider lowering --hop-sec.")

    LOGGER.debug("dotenv: %s", (dotenv_path or "<none>"))
    LOGGER.info("device=%s window=%.3f hop=%.3f pad_last=%s agg=%s topk=%d",
                args.device, args.window_sec, args.hop_sec, args.pad_last, args.agg, args.topk)
    LOGGER.debug("db_url=%r schema=%s head=%r labels_csv=%r", args.db_url, args.db_schema, args.head, args.labels_csv)

    root = pathlib.Path(args.audio)
    if root.is_file():
        ext = root.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            LOGGER.error("unsupported extension: %s. Supported: %s", ext, ", ".join(sorted(SUPPORTED_EXTS)))
            sys.exit(4)

    if args.head:
        hp = pathlib.Path(args.head)
        if not hp.exists():
            LOGGER.warning("head not found at %s; proceeding without head", hp.resolve())
            args.head = None

    # CNN14 is used for AudioSet top-k printouts (kept for parity)
    try:
        at = load_cnn14_model(args.checkpoint, args.checkpoint_url, device=args.device)
    except Exception as e:
        LOGGER.exception("failed to load model: %s", e); sys.exit(2)

    head = None
    head_classes = [
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
    head_expected_dim: Optional[int] = None
    if args.head:
        try:
            import joblib
            meta_path = pathlib.Path(f"{args.head}.meta.json")
            head = joblib.load(args.head)
            if meta_path.exists():
                head_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(head_meta, dict):
                    if "class_order" in head_meta:
                        head_classes = list(head_meta["class_order"])
                    if "backbone" in head_meta and head_meta["backbone"] != args.backbone:
                        LOGGER.warning("head backbone=%s != --backbone=%s", head_meta["backbone"], args.backbone)
                    if "embedding_dim" in head_meta:
                        head_expected_dim = int(head_meta["embedding_dim"])
            LOGGER.info("loaded head: %s (classes=%s)", args.head, head_classes)
        except Exception as e:
            LOGGER.warning("failed to load head '%s': %s", args.head, e)
            head = None

    files = discover_audio_files(root)
    if not files:
        LOGGER.warning("no audio files under: %s", root)
        LOGGER.info("supported: %s", ", ".join(sorted(SUPPORTED_EXTS)))
        sys.exit(0)

    override_labels: Optional[List[str]] = None
    if args.labels_csv:
        try:
            override_labels = load_labels_from_csv(args.labels_csv)
        except Exception as e:
            LOGGER.warning("failed to load labels CSV '%s': %s; ignoring override", args.labels_csv, e)
            override_labels = None

    conn = None
    run_id = str(uuid.uuid4())

    try:
        if args.write_db:
            if not args.db_url:
                LOGGER.error("--write-db requires --db-url or env DB_URL"); sys.exit(3)
            from classification.db.pg import open_db, upsert_run
            from os import getenv
            LOGGER.debug("DB_URL used by app: %r (schema=%s)", args.db_url, args.db_schema)
            conn = open_db(args.db_url, schema=args.db_schema)
            upsert_run(conn, dict(
                run_id=run_id,
                model_name=(
                    "VGGish" if args.backbone == "vggish"
                    else "Fusion (CNN14+VGGish)" if args.backbone == "fusion"
                    else "AST" if args.backbone == "ast"
                    else "CNN14 (PANNs)"
                ),
                checkpoint=(args.checkpoint if args.backbone in ("cnn14", "fusion") else ""),
                head_path=(args.head or ""),
                labels_csv=(args.labels_csv or ""),
                window_sec=float(args.window_sec),
                hop_sec=float(args.hop_sec),
                pad_last=bool(args.pad_last),
                agg=args.agg,
                topk=int(args.topk),
                device=args.device,
                code_version=getenv("GIT_COMMIT", ""),
                notes=f"unknown_threshold={args.unknown_threshold}"
            ))

        t_all_start = time.perf_counter()
        topk_file = max(1, int(args.topk))

        for f in files:
            try:
                t_file_start = time.perf_counter()

                wav = load_audio(str(f), target_sr=SAMPLE_RATE)
                duration_s = float(len(wav) / SAMPLE_RATE)
                try:
                    size_bytes = f.stat().st_size
                except Exception:
                    size_bytes = None

                windows = segment_waveform(
                    wav, sr=SAMPLE_RATE,
                    window_sec=float(args.window_sec),
                    hop_sec=float(args.hop_sec),
                    pad_last=bool(args.pad_last),
                )
                if not windows:
                    LOGGER.warning("no windows for %s", f.name)
                    continue

                per_window_probs: List[np.ndarray] = []
                per_window_labels: Optional[List[str]] = None
                per_window_head: List[Optional[np.ndarray]] = []

                for (t0, t1, seg) in windows:
                    probs, labs, emb = run_inference_with_embedding(at, seg)
                    if per_window_labels is None:
                        if override_labels and len(override_labels) == probs.size:
                            per_window_labels = override_labels
                        else:
                            if override_labels and len(override_labels) != probs.size:
                                LOGGER.warning("labels_csv length mismatch (got %d, expected %d); using model labels",
                                               len(override_labels) if override_labels else -1, int(probs.size))
                            per_window_labels = labs
                    per_window_probs.append(probs)

                    # Optional Head inference
                    hp: Optional[np.ndarray] = None
                    if head is not None:
                        try:
                            if args.backbone == "vggish":
                                v = run_vggish_embeddings(seg, SAMPLE_RATE,
                                                          window_sec=float(args.window_sec),
                                                          hop_sec=float(args.window_sec),
                                                          device=args.device)
                                emb_for_head = v[0]  # (128,)
                            elif args.backbone == "cnn14":
                                emb_for_head = emb if emb is not None else run_cnn14_embedding(at, seg)
                                emb_for_head = np.asarray(emb_for_head, dtype=np.float32).reshape(-1)
                            elif args.backbone == "fusion":
                                emb_c = emb if emb is not None else run_cnn14_embedding(at, seg)
                                emb_c = np.asarray(emb_c, dtype=np.float32).reshape(-1)
                                v = run_vggish_embeddings(seg, SAMPLE_RATE,
                                                          window_sec=float(args.window_sec),
                                                          hop_sec=float(args.window_sec),
                                                          device=args.device)
                                emb_v = v[0].astype(np.float32, copy=False)
                                emb_for_head = np.concatenate([emb_c, emb_v], axis=0).astype(np.float32, copy=False)
                            elif args.backbone == "ast":
                                emb_for_head = run_ast_embedding(seg, sr=SAMPLE_RATE, device=args.device,
                                                                 model_path=args.ast_model_dir, local_only=True)
                            else:
                                raise ValueError(f"Unsupported backbone: {args.backbone}")

                            emb_for_head = np.asarray(emb_for_head, dtype=np.float32).reshape(-1)
                            if (head_expected_dim is not None) and (emb_for_head.size != head_expected_dim):
                                LOGGER.warning("head expects embedding_dim=%d but got %d (backbone=%s); skipping window",
                                               head_expected_dim, emb_for_head.size, args.backbone)
                                hp = None
                            else:
                                hp = head.predict_proba(emb_for_head.reshape(1, -1))[0]
                        except Exception as e:
                            LOGGER.warning("head inference failed for window %.2f-%.2f: %s", t0, t1, e)
                            hp = None

                    per_window_head.append(hp)

                if per_window_labels is None:
                    LOGGER.error("no labels for %s", f.name)
                    continue

                # AudioSet top-k (kept for visibility)
                P = np.stack(per_window_probs, axis=0)
                agg_clipwise = aggregate_matrix(P, mode=args.agg)
                if args.agg == "max":
                    agg_clipwise = softmax_1d(agg_clipwise)
                idx_sorted = agg_clipwise.argsort()[::-1][:topk_file]
                top_pairs_file = [(per_window_labels[i], float(agg_clipwise[i])) for i in idx_sorted]

                print(f"\n========== {f.name} ==========")
                print(f"Windows: {len(windows)}  (window={args.window_sec:.2f}s, hop={args.hop_sec:.2f}s, agg={args.agg})")
                print("\nFile-level Top predictions (AudioSet, aggregated):")
                for i, (lab, p) in enumerate(top_pairs_file, 1):
                    print(f" {i:2d}. {lab:40s} {p:7.4f}")

                # Head aggregation (multi-class)
                agg_head = None
                pred_label = None
                pred_prob: Optional[float] = None
                is_another = False

                if head is not None and any(hp is not None for hp in per_window_head):
                    valid_hps = [hp for hp in per_window_head if hp is not None]
                    H = np.stack(valid_hps, axis=0)
                    agg_head = aggregate_matrix(H, mode=args.agg)
                    if args.agg == "max":
                        agg_head = softmax_1d(agg_head)

                    # Decide final label with unknown fallback
                    k = int(np.argmax(agg_head))
                    pred_label = head_classes[k]
                    pred_prob = float(agg_head[k])
                    if pred_prob < float(args.unknown_threshold):
                        pred_label = "another"
                        is_another = True

                    print("\nFile-level Head (multi-class) probabilities (aggregated):")
                    for cls, p in zip(head_classes, agg_head):
                        print(f"- {cls:<16} {float(p):7.4f}")
                    print(f"\nFinal label: {pred_label}  (top1={head_classes[k]} prob={pred_prob:.4f}, threshold={args.unknown_threshold})")

                # DB write
                if conn is not None:
                    from classification.db.pg import upsert_file, upsert_file_aggregate
                    file_id = upsert_file(conn, str(f), duration_s, SAMPLE_RATE, size_bytes)

                    agg_row = dict(
                        run_id=run_id,
                        file_id=file_id,
                        audioset_topk_json={"topk": top_pairs_file},
                        head_probs_json=({c: float(p) for c, p in zip(head_classes, agg_head)} if agg_head is not None else None),
                        head_pred_label=(pred_label if pred_label is not None else None),
                        head_pred_prob=(pred_prob if pred_prob is not None else None),
                        head_unknown_threshold=float(args.unknown_threshold),
                        head_is_another=bool(is_another),
                        num_windows=len(windows),
                        agg_mode=args.agg,
                    )
                    upsert_file_aggregate(conn, agg_row)

                t_file_end = time.perf_counter()
                LOGGER.info("%s: %.2f sec", f.name, (t_file_end - t_file_start))

            except Exception as e:
                LOGGER.exception("failed on %s: %s", f, e)

        t_all_end = time.perf_counter()
        LOGGER.info("total for %d files: %.2f sec", len(files), (t_all_end - t_all_start))

    finally:
        if conn is not None:
            try:
                from classification.db.pg import finish_run
                finish_run(conn, run_id)
                LOGGER.info("wrote results to PostgreSQL (schema=%s, run_id=%s)", args.db_schema, run_id)
            except Exception as e:
                LOGGER.exception("failed to finalize DB run: %s", e)

if __name__ == "__main__":  # pragma: no cover
    main()
