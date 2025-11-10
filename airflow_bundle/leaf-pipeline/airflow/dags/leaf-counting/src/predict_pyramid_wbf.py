from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime

import cv2
import numpy as np
from ultralytics import YOLO

from common import iter_images, ensure_dir, draw_boxes

try:
    from minio_io import get_client, ensure_bucket, put_png, put_json
except Exception:
    get_client = ensure_bucket = put_png = put_json = None


# ----------------- WBF utils -----------------
def iou_xyxy(a: np.ndarray, b: np.ndarray) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter + 1e-9
    return inter / union


def wbf(boxes: List[np.ndarray], scores: List[float], iou_thr: float = 0.55) -> tuple[list[np.ndarray], list[float]]:
    """Very small WBF: קיבוץ לפי IoU>=thr, ממוצע משוקלל לפי conf."""
    used = [False] * len(boxes)
    out_boxes, out_scores = [], []
    for i in range(len(boxes)):
        if used[i]:
            continue
        group_idxs = [i]
        used[i] = True
        for j in range(i + 1, len(boxes)):
            if used[j]:
                continue
            if iou_xyxy(boxes[i], boxes[j]) >= iou_thr:
                group_idxs.append(j)
                used[j] = True
        bs = np.array([boxes[k] for k in group_idxs], dtype=float)
        ws = np.array([scores[k] for k in group_idxs], dtype=float)
        wsum = ws.sum() + 1e-9
        avg = (bs * ws[:, None]).sum(axis=0) / wsum
        out_boxes.append(avg)
        out_scores.append(float(ws.max()))
    return out_boxes, out_scores


# ----------------- multi-scale predict -----------------
def predict_at_scales(model: YOLO, img_bgr: np.ndarray, scales: List[float], conf: float, imgsz: int, device: str):
    H, W = img_bgr.shape[:2]
    all_boxes, all_scores, all_classes = [], [], []
    for s in scales:
        if s == 1.0:
            resized = img_bgr
            rx, ry = 1.0, 1.0
        else:
            newW, newH = int(W * s), int(H * s)
            resized = cv2.resize(img_bgr, (newW, newH), interpolation=cv2.INTER_LINEAR)
            rx, ry = 1.0 / s, 1.0 / s

        res = model.predict(source=resized, conf=conf, imgsz=imgsz, device=device, verbose=False)[0]
        if res.boxes is None or len(res.boxes) == 0:
            continue
        for b in res.boxes:
            xyxy = b.xyxy.cpu().numpy().reshape(-1)
            conf_i = float(b.conf.cpu().numpy().reshape(-1)[0])
            cls_i = float(b.cls.cpu().numpy().reshape(-1)[0]) if b.cls is not None else 0.0
            x1, y1, x2, y2 = xyxy
            # החזרה לקואורדינטות המקור
            x1, y1, x2, y2 = x1 * rx, y1 * ry, x2 * rx, y2 * ry
            all_boxes.append(np.array([x1, y1, x2, y2], dtype=float))
            all_scores.append(conf_i)
            all_classes.append(int(cls_i))
    return all_boxes, all_scores, all_classes


# ----------------- main runner -----------------
def run(inp: Path, out_dir: Path, weights: Path,
        scales: List[float], conf: float = 0.25, iou_thr: float = 0.55,
        imgsz: int = 896, device: str = "cpu",
        minio_endpoint: Optional[str] = None, minio_access: Optional[str] = None,
        minio_secret: Optional[str] = None, minio_bucket: Optional[str] = None,
        minio_prefix: str = "PREDICT_PWB", minio_secure: bool = False,
        run_id: Optional[str] = None):

    run_id = run_id or datetime.now().strftime("%Y/%m/%d/%H%M")

    out_dir = ensure_dir(out_dir)
    overlay_root = ensure_dir(out_dir / "overlay")
    json_root = ensure_dir(out_dir / "json")

    cli = None
    if minio_endpoint and minio_access and minio_secret and minio_bucket:
        if get_client is None:
            raise SystemExit("[ERR] חסר minio או minio_io.")
        cli = get_client(minio_endpoint, minio_access, minio_secret, secure=minio_secure)
        ensure_bucket(cli, minio_bucket)

    model = YOLO(str(weights))
    images = list(iter_images(inp))
    if not images:
        raise SystemExit(f"[ERR] No images under: {inp}")

    for p in images:
        img = cv2.imread(str(p))
        if img is None:
            print(f"[WARN] can't read: {p}")
            continue
        H, W = img.shape[:2]

        # נתיב יחסי לשורש הקלט
        rel_path = str(p.relative_to(inp)) if inp.is_dir() else p.name
        rel_parent = str(Path(rel_path).parent)
        rel_stem = Path(rel_path).stem

        boxes, scores, classes = predict_at_scales(model, img, scales, conf, imgsz, device)

        # WBF לכל מחלקה בנפרד
        merged = []
        for cls in sorted(set(classes)):
            idxs = [i for i, c in enumerate(classes) if c == cls]
            if not idxs:
                continue
            bcls = [boxes[i] for i in idxs]
            scls = [scores[i] for i in idxs]
            mbox, mscore = wbf(bcls, scls, iou_thr=iou_thr)
            for bb, ss in zip(mbox, mscore):
                x1, y1, x2, y2 = [float(max(0, v)) for v in bb]
                x1, y1 = min(x1, W - 1), min(y1, H - 1)
                x2, y2 = min(x2, W - 1), min(y2, H - 1)
                merged.append([x1, y1, x2, y2, float(ss), float(cls)])

        # תיקיות פלט משוקפות
        overlay_dir = ensure_dir(overlay_root / rel_parent)
        json_dir = ensure_dir(json_root / rel_parent)

        j = {
            "image": p.name,
            "rel_path": rel_path,
            "source_path": str(p.resolve()),
            "width": W, "height": H,
            "boxes": merged
        }
        jpath = json_dir / f"{rel_stem}.json"
        jpath.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")

        overlay = draw_boxes(img, merged)
        cv2.imwrite(str(overlay_dir / p.name), overlay)

        # MinIO (תאריך/שעה קודם, אח"כ שלב)
        if cli:
            base = f"{run_id}/{minio_prefix}"
            json_key = f"{base}/json/{rel_parent}/{rel_stem}.json" if rel_parent != "." else f"{base}/json/{rel_stem}.json"
            ov_key = f"{base}/overlay/{rel_parent}/{p.name}" if rel_parent != "." else f"{base}/overlay/{p.name}"
            put_json(cli, minio_bucket, json_key, j)
            put_png(cli, minio_bucket, ov_key, overlay)

        print(f"[OK] {rel_path} WBF boxes={len(merged)} -> {jpath.relative_to(out_dir)}")


def parse_scales(s: str) -> List[float]:
    return [float(x) for x in s.split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser(description="YOLO multi-scale + WBF (+optional MinIO)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--scales", default="0.75,1.0,1.25", help="comma-separated, e.g. 0.5,1.0,1.5")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.55, help="WBF IoU threshold")
    ap.add_argument("--imgsz", type=int, default=896)
    ap.add_argument("--device", default="cpu")

    # MinIO
    ap.add_argument("--minio-endpoint", default=None)
    ap.add_argument("--minio-access", default=None)
    ap.add_argument("--minio-secret", default=None)
    ap.add_argument("--minio-bucket", default=None)
    ap.add_argument("--minio-prefix", default="PREDICT_PWB")
    ap.add_argument("--minio-secure", action="store_true")

    # Run grouping
    ap.add_argument("--run-id", default=None, help="תיקיית הריצה ב-MinIO (ברירת מחדל: YYYY/MM/DD/HHmm)")

    args = ap.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y/%m/%d/%H%M")
    run(
        inp=Path(args.input),
        out_dir=Path(args.out),
        weights=Path(args.weights),
        scales=parse_scales(args.scales),
        conf=args.conf,
        iou_thr=args.iou,
        imgsz=args.imgsz,
        device=args.device,
        minio_endpoint=args.minio_endpoint,
        minio_access=args.minio_access,
        minio_secret=args.minio_secret,
        minio_bucket=args.minio_bucket,
        minio_prefix=args.minio_prefix,
        minio_secure=args.minio_secure,
        run_id=run_id,
    )


if __name__ == "__main__":
    main()
