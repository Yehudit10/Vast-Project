import cv2
import argparse
from pathlib import Path

CLASS_ID = 0
IMG_EXTS = {".jpg", ".jpeg", ".png"}

def load_existing_boxes(lbl_path, W, H):
    boxes = []
    if lbl_path.exists():
        text = lbl_path.read_text().strip()
        if not text:
            return boxes  # label ריק
        for line in text.splitlines():
            parts = line.strip().split()
            if len(parts) != 5:
                continue
            _, xc, yc, w, h = map(float, parts)
            x1 = int((xc - w/2) * W); y1 = int((yc - h/2) * H)
            x2 = int((xc + w/2) * W); y2 = int((yc + h/2) * H)
            boxes.append((x1, y1, x2, y2))
    return boxes

def save_boxes(lbl_path, boxes, W, H):
    lines = []
    for (x1, y1, x2, y2) in boxes:
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(W-1, x2), min(H-1, y2)
        xc = ((x1 + x2) / 2) / W
        yc = ((y1 + y2) / 2) / H
        w  = (x2 - x1) / W
        h  = (y2 - y1) / H
        lines.append(f"{CLASS_ID} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}")
    lbl_path.write_text("\n".join(lines))

def annotate_split(root: Path, split: str, show_all: bool):
    img_dir = root / split / "images"
    lbl_dir = root / split / "labels"
    lbl_dir.mkdir(parents=True, exist_ok=True)

    candidates = []
    for p in sorted(img_dir.iterdir()):
        if p.suffix.lower() not in IMG_EXTS:
            continue
        lbl = lbl_dir / f"{p.stem}.txt"
        if show_all:
            candidates.append((p, lbl))
        else:
            # רק תמונות ללא txt או עם txt ריק
            if (not lbl.exists()) or (lbl.read_text().strip() == ""):
                candidates.append((p, lbl))

    if not candidates:
        print(f"[{split}] אין תמונות לא מתוייגות (או ריקות).")
        return

    drawing = False
    ix = iy = 0

    for img_path, lbl_path in candidates:
        img = cv2.imread(str(img_path))
        if img is None:
            print("skip:", img_path)
            continue
        H, W = img.shape[:2]
        boxes = load_existing_boxes(lbl_path, W, H)
        img_disp = img.copy()

        # צייר תיבות קיימות (אם יש)
        for (x1,y1,x2,y2) in boxes:
            cv2.rectangle(img_disp, (x1,y1), (x2,y2), (0,255,0), 2)

        def mouse(event, x, y, flags, param):
            nonlocal drawing, ix, iy, img_disp, boxes
            if event == cv2.EVENT_LBUTTONDOWN:
                drawing = True; ix, iy = x, y
            elif event == cv2.EVENT_LBUTTONUP:
                drawing = False
                x1, y1 = min(ix, x), min(iy, y)
                x2, y2 = max(ix, x), max(iy, y)
                boxes.append((x1, y1, x2, y2))
                cv2.rectangle(img_disp, (x1,y1), (x2,y2), (0,255,0), 2)

        win = "annotate (s=save, u=undo, c=clear, n=skip, q=quit)"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(win, mouse)

        while True:
            cv2.imshow(win, img_disp)
            key = cv2.waitKey(20) & 0xFF
            if key == ord('u') and boxes:
                boxes.pop()
                img_disp = img.copy()
                for (x1,y1,x2,y2) in boxes:
                    cv2.rectangle(img_disp, (x1,y1), (x2,y2), (0,255,0), 2)
            elif key == ord('c'):
                boxes = []
                img_disp = img.copy()
            elif key in (ord('s'), 13):  # s או Enter
                save_boxes(lbl_path, boxes, W, H)
                break
            elif key in (ord('n'), 27):  # n או Esc → דלג ללא שמירה
                break
            elif key == ord('q'):
                cv2.destroyAllWindows()
                return
        cv2.destroyAllWindows()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/fence_holes", help="שורש הדאטה")
    ap.add_argument("--split", default="train", choices=["train","valid","test"], help="על איזה split לעבוד")
    ap.add_argument("--all", action="store_true", help="להציג גם תמונות שכבר יש להן לייבל")
    args = ap.parse_args()
    annotate_split(Path(args.root), args.split, args.all)

if __name__ == "__main__":
    main()
