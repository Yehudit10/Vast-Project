from pathlib import Path

ROOT = Path("data/fence_holes")
for split in ["train","valid","test"]:
    img_dir = ROOT / split / "images"
    lbl_dir = ROOT / split / "labels"
    if not img_dir.exists(): 
        print(f"[{split}] אין תיקיית images, מדלג.")
        continue
    imgs = [p for p in img_dir.iterdir() if p.suffix.lower() in {".jpg",".jpeg",".png"}]
    pos = 0
    for img in imgs:
        txt = lbl_dir / f"{img.stem}.txt"
        if txt.exists() and txt.read_text().strip():
            pos += 1
    print(f"[{split}] images={len(imgs)}   positives(with at least one box)={pos}")
