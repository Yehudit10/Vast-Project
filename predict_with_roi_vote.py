# predict_with_roi_vote.py
# אינפרנס על תיקיית תמונות עם:
# 1) סף conf
# 2) ROI עם חפיפה מינימלית
# 3) N מתוך M + cooldown ליצירת אירועי התרעה
#
# פלט: תמונות מסומנות + alerts.csv עם רשימת אירועים.

from ultralytics import YOLO
from pathlib import Path
from collections import deque
import argparse, csv, cv2
import numpy as np

IMG_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

def overlap_ratio_with_roi(box, H, ymin_frac, ymax_frac):
    x1,y1,x2,y2 = box
    box_h = max(0.0, y2 - y1)
    if box_h <= 0: return 0.0
    roi_y1 = ymin_frac * H
    roi_y2 = ymax_frac * H
    inter_h = max(0.0, min(y2, roi_y2) - max(y1, roi_y1))
    return inter_h / (box_h + 1e-9)

def filter_boxes_by_roi_overlap(boxes, H, ymin_frac, ymax_frac, min_overlap=0.30):
    kept=[]
    for b in boxes:
        if overlap_ratio_with_roi(b, H, ymin_frac, ymax_frac) >= min_overlap:
            kept.append(b)
    return kept

class VoteNM:
    def __init__(self, N=2, M=3, cooldown_frames=10):
        self.N=N; self.M=M
        self.buf=deque(maxlen=M)
        self.cooldown=cooldown_frames
        self.cd=0

    def update(self, detected: bool):
        if self.cd>0:
            self.cd-=1
        self.buf.append(1 if detected else 0)
        if len(self.buf)==self.buf.maxlen and sum(self.buf)>=self.N and self.cd==0:
            self.cd=self.cooldown
            return True
        return False

def draw_roi(img, ymin_frac, ymax_frac, color=(255,0,0)):
    H, W = img.shape[:2]
    y1 = int(ymin_frac * H); y2 = int(ymax_frac * H)
    cv2.rectangle(img, (0,y1), (W,y2), color, 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True, help="path to best.pt")
    ap.add_argument("--source", required=True, help="folder of images (sorted by name) or a single image")
    ap.add_argument("--out_dir", default="realtime_preds", help="output folder")
    ap.add_argument("--conf", type=float, default=0.35, help="confidence threshold")
    ap.add_argument("--roi", default="none", help="e.g. 0.20-0.85 or 'none' to disable ROI")
    ap.add_argument("--min_overlap", type=float, default=0.30, help="minimal vertical overlap with ROI")
    ap.add_argument("--N", type=int, default=2, help="vote N of M")
    ap.add_argument("--M", type=int, default=3, help="vote window size")
    ap.add_argument("--cooldown", type=int, default=10, help="frames to wait after firing an alert")
    args = ap.parse_args()

    model = YOLO(args.weights)
    src = Path(args.source)
    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)

    if args.roi.lower() == "none":
        use_roi = False
        ymin_frac = 0.0; ymax_frac = 1.0
    else:
        use_roi = True
        ymin_frac, ymax_frac = map(float, args.roi.split("-"))

    # מקורות
    if src.is_file():
        images = [src]
    else:
        images = sorted([p for p in src.iterdir() if p.suffix.lower() in IMG_SUFFIXES])

    voter = VoteNM(N=args.N, M=args.M, cooldown_frames=args.cooldown)

    # CSV של אירועים
    alerts_csv = out / "alerts.csv"
    with alerts_csv.open("w", newline="", encoding="utf-8") as fcsv:
        w = csv.DictWriter(fcsv, fieldnames=[
            "index","image","detected_boxes","fired_alert"
        ])
        w.writeheader()

        for i, im in enumerate(images):
            r = model.predict(source=str(im), conf=args.conf, iou=0.5, save=False, verbose=False)[0]
            H, W = r.orig_shape[0], r.orig_shape[1]

            boxes=[]
            if r.boxes is not None and len(r.boxes)>0:
                for b in r.boxes.xyxy.cpu().numpy().tolist():
                    boxes.append(b)

            if use_roi:
                boxes = filter_boxes_by_roi_overlap(boxes, H, ymin_frac, ymax_frac, min_overlap=args.min_overlap)

            detected = len(boxes) > 0
            fired = voter.update(detected)

            # ציור ושמירה
            img = cv2.imread(str(im))
            if use_roi:
                draw_roi(img, ymin_frac, ymax_frac)
            for b in boxes:
                x1,y1,x2,y2 = map(int, b)
                cv2.rectangle(img,(x1,y1),(x2,y2),(0,255,0),2)
            if fired:
                cv2.putText(img, "ALERT", (10,30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,0,255), 2, cv2.LINE_AA)

            out_path = out / f"{i:06d}_{im.stem}.jpg"
            cv2.imwrite(str(out_path), img)

            w.writerow({
                "index": i,
                "image": str(im),
                "detected_boxes": len(boxes),
                "fired_alert": int(fired)
            })

    print(f"Saved results to: {out}")

if __name__ == "__main__":
    main()
