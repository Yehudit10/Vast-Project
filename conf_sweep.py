# conf_sweep.py
from pathlib import Path
from ultralytics import YOLO
import argparse
import csv
import json

def iou_xyxy(a, b):
    # a,b = [x1,y1,x2,y2]
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (a[2]-a[0])*(a[3]-a[1])
    area_b = (b[2]-b[0])*(b[3]-b[1])
    union = area_a + area_b - inter + 1e-9
    return inter / union

def read_labels(lbl_path, W, H):
    boxes=[]
    if not lbl_path.exists():
        return boxes
    txt = lbl_path.read_text().strip()
    if not txt:
        return boxes
    for line in txt.splitlines():
        cid, xc, yc, w, h = map(float, line.split())
        x1=(xc-w/2)*W; y1=(yc-h/2)*H; x2=(xc+w/2)*W; y2=(yc+h/2)*H
        boxes.append([x1,y1,x2,y2])
    return boxes

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--valid_images", default="data/fence_holes/valid/images")
    ap.add_argument("--valid_labels", default="data/fence_holes/valid/labels")
    ap.add_argument("--out_csv", default="conf_sweep_results.csv")
    ap.add_argument("--confs", default="0.25,0.35,0.45")
    ap.add_argument("--iou_thr", type=float, default=0.5)
    args = ap.parse_args()

    model = YOLO(args.weights)
    img_dir = Path(args.valid_images)
    lbl_dir = Path(args.valid_labels)

    confs = [float(x) for x in args.confs.split(",")]
    rows=[]

    imgs = sorted([p for p in img_dir.iterdir() if p.suffix.lower() in {".jpg",".jpeg",".png"}])
    for conf in confs:
        TP=FP=FN=0
        for img_path in imgs:
            r = model.predict(source=str(img_path), conf=conf, iou=0.5, save=False, verbose=False)[0]
            W, H = r.orig_shape[1], r.orig_shape[0]
            preds = []
            if r.boxes is not None and len(r.boxes) > 0:
                for b in r.boxes.xyxy.cpu().numpy().tolist():
                    preds.append(b)  # [x1,y1,x2,y2]

            gt = read_labels(lbl_dir / f"{img_path.stem}.txt", W, H)

            matched = set()
            # התאמות פשוטות לפי IoU
            for pb in preds:
                found = False
                for gi, gb in enumerate(gt):
                    if gi in matched: 
                        continue
                    if iou_xyxy(pb, gb) >= args.iou_thr:
                        TP += 1
                        matched.add(gi)
                        found = True
                        break
                if not found:
                    FP += 1
            FN += max(0, len(gt)-len(matched))

        prec = TP/(TP+FP+1e-9)
        rec  = TP/(TP+FN+1e-9)
        f1   = 2*prec*rec/(prec+rec+1e-9)
        rows.append({"conf":conf, "TP":TP, "FP":FP, "FN":FN, "Precision":prec, "Recall":rec, "F1":f1})

    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    print("Saved:", args.out_csv)
    print(json.dumps(rows, indent=2))

if __name__ == "__main__":
    main()
