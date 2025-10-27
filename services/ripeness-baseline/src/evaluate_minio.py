
"""
Evaluate the baseline (segment + heuristics) on images stored in MinIO.

Assumes MinIO layout like:
  imagery/apple/test/{unripe,ripe,overripe}/*.jpg|png|bmp|webp
  imagery/apple/train/{unripe,ripe,overripe}/*.jpg|png|bmp|webp

Outputs:
  - confusion_matrix.png
  - roc_curves.png
  - per_image.csv
  - metrics.json
"""

import os, io, csv, json, argparse, time
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import cv2 as cv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, roc_curve, auc

from minio import Minio
from minio.error import S3Error

from config import THRESHOLDS
from segment import segment_fruit
from heuristics import compute_features, classify_ripeness

LABELS = ["unripe", "ripe", "overripe"]
LABEL2IDX = {l:i for i,l in enumerate(LABELS)}

def _minio_client(url, access_key, secret_key):
    u = urlparse(url)
    secure = (u.scheme == "https")
    return Minio(u.netloc, access_key=access_key, secret_key=secret_key, secure=secure)

def _truth_from_key(key, anchor="apple"):
    parts = key.split("/")
    try:
        i = parts.index(anchor)
        truth = parts[i+2].lower()
        if truth == "rotten":
            truth = "overripe"
        return parts[i+1].lower(), truth  # split, truth
    except Exception:
        for p in parts:
            pp = p.lower()
            if pp in LABELS:
                return None, pp
        return None, None

def _scores_from_features(f):
    or_brown = max(0.0, (f.brown_ratio - THRESHOLDS["overripe_brown_ratio"]) / max(1e-6, (1.0 - THRESHOLDS["overripe_brown_ratio"])))
    or_dark  = max(0.0, (THRESHOLDS["overripe_min_v"] - f.mean_v) / max(1e-6, THRESHOLDS["overripe_min_v"]))
    s_overripe = float(np.clip(0.6*or_brown + 0.4*or_dark, 0.0, 1.0))

    hmin = THRESHOLDS["unripe_h_min"]; hmax = THRESHOLDS["unripe_h_max"]
    hmid = 0.5*(hmin+hmax); halfw = max(1e-6, 0.5*(hmax-hmin))
    dist = abs(f.mean_h - hmid) / halfw
    s_unripe = float(np.clip(1.0 - dist, 0.0, 1.0)) if (f.mean_h >= hmin-10 and f.mean_h <= hmax+10) else 0.0

    s_ripe = float(np.clip(1.0 - max(s_overripe, s_unripe), 0.0, 1.0))
    return np.array([s_unripe, s_ripe, s_overripe], dtype=np.float32)

def evaluate(minio_url, access_key, secret_key, bucket, prefix, outdir, fruit, limit=0, use_argmax=False):
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    client = _minio_client(minio_url, access_key, secret_key)

    if not client.bucket_exists(bucket):
        raise SystemExit(f"Bucket '{bucket}' does not exist")

    exts = (".jpg",".jpeg",".png",".bmp",".webp")
    objs = client.list_objects(bucket, prefix=prefix, recursive=True)
    import json
    thr = {}
    if args.thresholds_json:
        with open(args.thresholds_json, "r", encoding="utf-8") as f:
            thr = json.load(f)
    y_true, y_pred, y_scores, rows = [], [], [], []
    n = 0
    for o in objs:
        key = o.object_name
        if not key.lower().endswith(exts):
            continue
        split, truth = _truth_from_key(key, anchor=fruit)
        if truth not in LABELS:
            continue

        try:
            resp = client.get_object(bucket, key)
            data = resp.read()
            resp.close(); resp.release_conn()
        except S3Error as e:
            rows.append([key, truth, "", "", "S3Error", str(e)])
            continue

        img_arr = np.frombuffer(data, dtype=np.uint8)
        img = cv.imdecode(img_arr, cv.IMREAD_COLOR)
        if img is None:
            rows.append([key, truth, "", "", "DecodeError", "cv2.imdecode returned None"])
            continue

        mask, leaf_ratio = segment_fruit(img,fruit)
        feat = compute_features(img, mask)
        scores = _scores_from_features(feat)

        if use_argmax:
            labels = ["unripe", "ripe", "overripe"]
            pred_label = labels[int(np.argmax(scores))]
        else:
            pred_label = classify_ripeness(feat, thr if thr else THRESHOLDS).lower().replace("rotten","overripe")

        y_true.append(LABEL2IDX[truth])
        y_pred.append(LABEL2IDX.get(pred_label, -1))
        y_scores.append(scores)
        rows.append([key, truth, pred_label, float(scores[0]), float(scores[1]), float(scores[2])])

        n += 1
        if limit and n >= limit: break

    if not y_true:
        raise SystemExit("No images evaluated; check your prefix and bucket")

    y_true = np.array(y_true, dtype=int)
    y_pred = np.array(y_pred, dtype=int)
    y_scores = np.stack(y_scores, axis=0)

    acc = accuracy_score(y_true, y_pred)
    report = classification_report(y_true, y_pred, target_names=LABELS, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=[0,1,2])

    # Confusion matrix plot
    fig = plt.figure(figsize=(5,4))
    im = plt.imshow(cm, interpolation="nearest")
    plt.title("Confusion Matrix (baseline)")
    plt.colorbar(im)
    ticks = np.arange(len(LABELS))
    plt.xticks(ticks, LABELS, rotation=45, ha="right")
    plt.yticks(ticks, LABELS)
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            plt.text(j, i, str(cm[i, j]), ha="center", va="center")
    plt.tight_layout()
    plt.savefig(outdir/"confusion_matrix.png", dpi=160)
    plt.close(fig)

    # ROC curves
    fig = plt.figure(figsize=(5,4))
    for i, name in enumerate(LABELS):
        y_true_bin = (y_true == i).astype(int)
        fpr, tpr, _ = roc_curve(y_true_bin, y_scores[:, i])
        roc_auc = auc(fpr, tpr)
        plt.plot(fpr, tpr, label=f"{name} (AUC={roc_auc:.3f})")
    plt.plot([0,1], [0,1], "--")
    plt.xlabel("False Positive Rate"); plt.ylabel("True Positive Rate")
    plt.title("ROC (one-vs-rest)"); plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(outdir/"roc_curves.png", dpi=160); plt.close(fig)

    # per-image CSV
    with open(outdir/"per_image.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["object_key","truth","pred","score_unripe","score_ripe","score_overripe"])
        w.writerows(rows)

    # metrics JSON
    metrics = {
        "accuracy": acc,
        "report": report,
        "confusion_matrix": cm.tolist(),
        "samples": int(len(y_true)),
        "prefix": prefix,
        "bucket": bucket,
    }
    with open(outdir/"metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print("\n=== Baseline Evaluation ===")
    print(f"Evaluated samples: {len(y_true)} | Accuracy: {acc:.3%}")
    for cls in LABELS:
        pr = report[cls]
        print(f"  {cls:9s}  P={pr['precision']:.3f}  R={pr['recall']:.3f}  F1={pr['f1-score']:.3f}  (n={int(pr['support'])})")
    print(f"\nSaved to: {outdir}")

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minio-url", required=True)
    ap.add_argument("--access-key", required=True)
    ap.add_argument("--secret-key", required=True)
    ap.add_argument("--bucket", default="imagery")
    ap.add_argument("--prefix", default="apple/test")
    ap.add_argument("--outdir", default="./eval/test")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--fruit", default="apple")
    ap.add_argument("--thresholds-json", default=None,
                help="Path to tuned thresholds JSON (optional)")
    ap.add_argument("--use-argmax", action="store_true",
                help="Use argmax over soft scores for prediction (diagnostic).")
    return ap.parse_args()

if __name__ == "__main__":
    args = parse_args()
    evaluate(args.minio_url, args.access_key, args.secret_key, args.bucket, args.prefix, args.outdir, args.fruit, args.limit, args.use_argmax)
