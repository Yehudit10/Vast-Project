import argparse
from pathlib import Path

def create_empty_labels(root: Path, splits, img_exts):
    total_imgs = total_lbls = created = 0
    for split in splits:
        img_dir = root / split / "images"
        lbl_dir = root / split / "labels"
        if not img_dir.exists():
            print(f"[{split}] אין תיקיית images, מדלג.")
            continue
        lbl_dir.mkdir(parents=True, exist_ok=True)

        imgs = [p for p in img_dir.iterdir() if p.suffix.lower() in img_exts]
        total_imgs += len(imgs)

        for img in imgs:
            stem = img.stem
            txt = lbl_dir / f"{stem}.txt"
            if txt.exists():
                total_lbls += 1
                continue
            # יוצר קובץ ריק = תמונה שלילית (אין אובייקטים)
            txt.touch()
            created += 1
            total_lbls += 1

        # בדיקת orphan labels (label בלי תמונה תואמת)
        label_files = [p for p in lbl_dir.glob("*.txt")]
        orphan = [p for p in label_files if not (img_dir / (p.stem + ".jpg")).exists()
                  and not (img_dir / (p.stem + ".jpeg")).exists()
                  and not (img_dir / (p.stem + ".png")).exists()]
        if orphan:
            print(f"[{split}] אזהרה: נמצאו {len(orphan)} קבצי label ללא תמונה תואמת (orphan).")

    print(f"\nסיכום:")
    print(f"- תמונות שנמצאו: {total_imgs}")
    print(f"- קבצי label לאחר הריצה: {total_lbls}")
    print(f"- קבצי label ריקים שנוצרו כעת: {created}")

def main():
    ap = argparse.ArgumentParser(description="צור קבצי txt ריקים לתמונות ללא labels (YOLO).")
    ap.add_argument("--root", default="data/fence_holes",
                    help="שורש הדאטה: data/fence_holes")
    ap.add_argument("--splits", nargs="+", default=["train", "valid", "test"],
                    help="תתי-התיקיות לעבור עליהן (ברירת מחדל: train valid test)")
    ap.add_argument("--exts", nargs="+", default=[".jpg", ".jpeg", ".png"],
                    help="סיומות תמונות נתמכות")
    args = ap.parse_args()

    root = Path(args.root)
    create_empty_labels(root, args.splits, {e.lower() for e in args.exts})

if __name__ == "__main__":
    main()
