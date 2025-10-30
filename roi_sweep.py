# roi_sweep.py
# Sweep לאזור עניין (ROI) לאורך ציר-Y + סינון לפי חפיפה חלקית עם ה-ROI
# מוציא CSV עם TP/FP/FN/Precision/Recall/F1 לכל ROI.

from ultralytics import YOLO
from pathlib import Path
import argparse
import csv

IMG_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

def iou_xyxy(a, b):
    """IoU בין שתי תיבות בפורמט [x1,y1,x2,y2] בפיקסלים"""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, (a[2] - a[0])) * max(0.0, (a[3] - a[1]))
    area_b = max(0.0, (b[2] - b[0])) * max(0.0, (b[3] - b[1]))
    return inter / (area_a + area_b - inter + 1e-9)

def read_labels(lbl_path: Path, W: int, H: int):
    """קורא קובץ YOLO txt (cls xc yc w h בנורמליזציה) ומחזיר תיבות בפיקסלים [x1,y1,x2,y2]."""
    if not lbl_path.exists():
        return []
    txt = lbl_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not txt:
        return []
    boxes = []
    for line in txt.splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            # מדלגים על שורות פגומות
            continue
        _, xc, yc, w, h = map(float, parts)
        x1 = (xc - w / 2) * W
        y1 = (yc - h / 2) * H
        x2 = (xc + w / 2) * W
        y2 = (yc + h / 2) * H
        boxes.append([x1, y1, x2, y2])
    return boxes

def overlap_ratio_with_roi(box, H, ymin_frac, ymax_frac):
    """יחס חפיפה אנכי של התיבה עם רצועת ה-ROI (בין 0 ל-1)."""
    x1, y1, x2, y2 = box
    box_h = max(0.0, y2 - y1)
    if box_h <= 0:
        return 0.0
    roi_y1 = ymin_frac * H
    roi_y2 = ymax_frac * H
    inter_h = max(0.0, min(y2, roi_y2) - max(y1, roi_y1))
    return inter_h / (box_h + 1e-9)

def filter_boxes_by_roi_overlap(boxes, H, ymin_frac, ymax_frac, min_overlap=0.30):
    """שומר תיבות שרמת החפיפה האנכית שלהן עם ה-ROI היא לפחות min_overlap."""
    kept = []
    for b in boxes:
        if overlap_ratio_with_roi(b, H, ymin_frac, ymax_frac) >= min_overlap:
            kept.append(b)
    return kept

def eval_roi(model, imgs, lbl_dir: Path, conf: float, iou_thr: float,
             roi_range: tuple[float, float], min_overlap: float):
    """מחשב TP/FP/FN/Precision/Recall/F1 עבור ROI בודד."""
    TP = FP = FN = 0
    ymin, ymax = roi_range
    for img_path in imgs:
        r = model.predict(
            source=str(img_path), conf=conf, iou=0.5, save=False, verbose=False
        )[0]
        H, W = r.orig_shape[0], r.orig_shape[1]

        preds = r.boxes.xyxy.cpu().numpy().tolist() if r.boxes is not None else []
        preds = filter_boxes_by_roi_overlap(preds, H, ymin, ymax, min_overlap=min_overlap)

        gt = read_labels(lbl_dir / f"{img_path.stem}.txt", W, H)

        matched = set()
        for pb in preds:
            found = False
            for gi, gb in enumerate(gt):
                if gi in matched:
                    continue
                if iou_xyxy(pb, gb) >= iou_thr:
                    TP += 1
                    matched.add(gi)
                    found = True
                    break
            if not found:
                FP += 1
        FN += max(0, len(gt) - len(matched))

    precision = TP / (TP + FP + 1e-9)
    recall = TP / (TP + FN + 1e-9)
    f1 = 2 * precision * recall / (precision + recall + 1e-9)
    return TP, FP, FN, precision, recall, f1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True, help="נתיב למודל best.pt")
    ap.add_argument("--valid_images", default="data/fence_holes/valid/images")
    ap.add_argument("--valid_labels", default="data/fence_holes/valid/labels")
    ap.add_argument("--conf", type=float, default=0.35, help="סף confidence לבדיקה")
    ap.add_argument("--iou_thr", type=float, default=0.5, help="IoU מול ה-GT לצורך TP")
    ap.add_argument("--min_overlap", type=float, default=0.30, help="חפיפה אנכית מינימלית של תיבה עם ה-ROI")
    ap.add_argument("--rois", default="0.20-0.85,0.25-0.85,0.25-0.80,0.30-0.80,0.30-0.75")
    ap.add_argument("--out_csv", default="roi_sweep_y8n.csv")
    args = ap.parse_args()

    model = YOLO(args.weights)
    img_dir = Path(args.valid_images)
    lbl_dir = Path(args.valid_labels)
    imgs = sorted([p for p in img_dir.iterdir() if p.suffix.lower() in IMG_SUFFIXES])

    roi_specs = []
    for rs in args.rois.split(","):
        rs = rs.strip()
        if not rs:
            continue
        ymin, ymax = map(float, rs.split("-"))
        roi_specs.append((rs, (ymin, ymax)))

    rows = []
    for rs_text, (ymin, ymax) in roi_specs:
        TP, FP, FN, prec, rec, f1 = eval_roi(
            model, imgs, lbl_dir, args.conf, args.iou_thr, (ymin, ymax), args.min_overlap
        )
        rows.append({
            "roi": rs_text,
            "min_overlap": args.min_overlap,
            "TP": TP,
            "FP": FP,
            "FN": FN,
            "Precision": prec,
            "Recall": rec,
            "F1": f1
        })
        print(f"[ROI {rs_text}] overlap>={args.min_overlap:.2f}  TP={TP} FP={FP} FN={FN}  "
              f"Prec={prec:.3f} Rec={rec:.3f} F1={f1:.3f}")

    # כתיבת CSV
    out = Path(args.out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        fieldnames = list(rows[0].keys()) if rows else ["roi","min_overlap","TP","FP","FN","Precision","Recall","F1"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print("Saved:", str(out))

if __name__ == "__main__":
    main()
