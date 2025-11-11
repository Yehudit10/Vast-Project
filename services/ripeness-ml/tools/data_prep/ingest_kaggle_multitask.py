
import argparse, csv, random
from pathlib import Path

IMG_EXT = {".jpg",".jpeg",".png",".bmp",".tif",".tiff",".webp"}

RIPENESS_MAP = {
    "unripe": "unripe",
    "fresh":  "ripe",   
    "ripe":   "ripe",
    "rotten": "overripe",
}

FRUIT_KEYS = ["apple", "banana", "orange", "pineapple"]

def detect_from_path(p: Path):
    names = [pp.name.lower().replace(" ", "").replace("_","") for pp in [p] + list(p.parents)]
    fruit = None
    ripeness = None

    for n in names:
        for fk in FRUIT_KEYS:
            if fk in n:
                fruit = fk
                break
        for key, mapped in RIPENESS_MAP.items():
            if key in n:
                ripeness = mapped
                break
        if fruit and ripeness:
            return fruit, ripeness
    return fruit, ripeness 

def gather(root: Path):
    rows = []  # (path, fruit, ripeness)
    for fp in root.rglob("*"):
        if fp.is_file() and fp.suffix.lower() in IMG_EXT:
            fruit, ripeness = detect_from_path(fp)
            if fruit and ripeness:
                rows.append((fp.resolve().as_posix(), fruit, ripeness))
    return rows

def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path","fruit","ripeness"])
        w.writerows(rows)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Create CSVs (train/val/test) with path,fruit,ripeness from Kaggle folders")
    ap.add_argument("--src", required=True, help="path to .../dataset (the folder that contains train/ and test/)")
    ap.add_argument("--outdir", default="data_mt", help="output folder for CSVs")
    ap.add_argument("--split", default="0.8,0.2,0.0", help="train,val,test ratios")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    root = Path(args.src).resolve()
    all_rows = gather(root)
    if not all_rows:
        raise SystemExit(f"No images found under: {root}. Check --src path.")

    random.seed(args.seed)
    random.shuffle(all_rows)

    tr, va, te = [float(x) for x in args.split.split(",")]
    assert abs(tr+va+te - 1.0) < 1e-6, "--split must sum to 1.0"
    n = len(all_rows); ntr = int(tr*n); nv = int(va*n)
    rows_tr = all_rows[:ntr]; rows_va = all_rows[ntr:ntr+nv]; rows_te = all_rows[ntr+nv:]

    out = Path(args.outdir)
    write_csv(out/"train.csv", rows_tr)
    write_csv(out/"val.csv",   rows_va)
    write_csv(out/"test.csv",  rows_te)

    print(f"Saved CSVs in {out.resolve()}")
    print(f"  train.csv: {len(rows_tr)}")
    print(f"  val.csv:   {len(rows_va)}")
    print(f"  test.csv:  {len(rows_te)}")
