from __future__ import annotations
import json, argparse
from pathlib import Path
from typing import Optional
import cv2
from common import ensure_dir
from datetime import datetime

try:
    from minio_io import get_client, ensure_bucket, put_png
except Exception:
    get_client = ensure_bucket = put_png = None


def _load_jsons(inp: Path):
    jdir = inp / "json"
    if not jdir.exists():
        raise SystemExit(f"[ERR] Expected JSON dir not found: {jdir} (run detect_only.py first)")
  
    for jp in sorted(jdir.rglob("*.json")):
        with jp.open("r", encoding="utf-8") as f:
            j = json.load(f)
        yield jp, j

def _safe_crop(img, x1, y1, x2, y2):
    h, w = img.shape[:2]
    x1 = max(0, min(w-1, int(x1))); y1 = max(0, min(h-1, int(y1)))
    x2 = max(0, min(w-1, int(x2))); y2 = max(0, min(h-1, int(y2)))
    if x2 <= x1: x2 = min(w-1, x1+1)
    if y2 <= y1: y2 = min(h-1, y1+1)
    return img[y1:y2, x1:x2]


def run_crop(inp: Path, out_dir: Path, size: int=224, margin: float=0.1, min_wh: int=8,
             orig_dir: Optional[Path]=None, flat: bool=False,
             minio_endpoint: Optional[str]=None, minio_access: Optional[str]=None,
             minio_secret: Optional[str]=None, minio_bucket: Optional[str]=None,
             minio_prefix: str="CROP", minio_secure: bool=False,
             run_id: Optional[str]=None):
    run_id = run_id or datetime.now().strftime("%Y/%m/%d/%H%M")
    out_dir = ensure_dir(out_dir)

    cli = None
    if minio_endpoint and minio_access and minio_secret and minio_bucket:
        if get_client is None:
            raise SystemExit("[ERR] חסר minio או minio_io.")
        cli = get_client(minio_endpoint, minio_access, minio_secret, secure=minio_secure)
        ensure_bucket(cli, minio_bucket)

    count = 0
    for jp, j in _load_jsons(inp):
       
        if "source_path" in j:
            img_path = Path(j["source_path"])
            rel_path = j.get("rel_path", j["image"])
        elif "rel_path" in j:
            if orig_dir is None:
                raise SystemExit("[ERR] JSON מכיל רק rel_path; ספקי --orig כדי למצוא את קובץ המקור")
            img_path = Path(orig_dir) / j["rel_path"]
            rel_path = j["rel_path"]
        else:
            if orig_dir is None:
                raise SystemExit("[ERR] JSON חסר source_path/rel_path; ספקי --orig ותתאימי לשמות image")
            img_path = Path(orig_dir) / j["image"]
            rel_path = j["image"]

        if not img_path.exists():
            print(f"[WARN] Original image not found: {img_path}, skipping")
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            print(f"[WARN] Can't read image: {img_path}")
            continue

        rel_parent = str(Path(rel_path).parent)
        rel_stem   = Path(rel_path).stem

       
        if flat:
            dest_dir = ensure_dir(out_dir)
            minio_subprefix = minio_prefix
        else:
            dest_dir = ensure_dir(out_dir / rel_parent / rel_stem)
            minio_subprefix = f"{minio_prefix}/{rel_parent}/{rel_stem}" if rel_parent != "." else f"{minio_prefix}/{rel_stem}"

        for i, (x1,y1,x2,y2,conf,cls_id) in enumerate(j.get("boxes", [])):
            w = x2 - x1; h = y2 - y1
            if w < min_wh or h < min_wh:
                continue
            cx = (x1 + x2) * 0.5; cy = (y1 + y2) * 0.5
            half = max(w, h) * 0.5 * (1.0 + margin)
            crop = _safe_crop(img, cx-half, cy-half, cx+half, cy+half)
            if crop.size == 0:
                continue
            crop_resized = cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)
            out_name = f"det{i:03d}_cls{int(cls_id)}_{conf:.2f}.png"
            cv2.imwrite(str(dest_dir / out_name), crop_resized)
            count += 1

            if cli:
                base = f"{run_id}/{minio_prefix}"  # תאריך/שעה קודם, אח"כ CROP
                key  = f"{base}/{rel_parent}/{rel_stem}/{out_name}" if rel_parent != "." else f"{base}/{rel_stem}/{out_name}"
                put_png(cli, minio_bucket, key, crop_resized)

                put_png(cli, minio_bucket, f"{minio_subprefix}/{out_name}", crop_resized)

    print(f"[DONE] Saved {count} crops under: {out_dir} (flat={flat})")

def main():
    ap = argparse.ArgumentParser(description="Create square crops from detection JSON results (+optional MinIO).")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--orig", default=None, help="דרוש רק אם JSON חסר source_path")
    ap.add_argument("--size", type=int, default=224)
    ap.add_argument("--margin", type=float, default=0.1)
    ap.add_argument("--min-wh", type=int, default=8)
    ap.add_argument("--flat", action="store_true")

    ap.add_argument("--minio-endpoint", default=None)
    ap.add_argument("--minio-access",   default=None)
    ap.add_argument("--minio-secret",   default=None)
    ap.add_argument("--minio-bucket",   default=None)
    ap.add_argument("--minio-prefix",   default="crops")
    ap.add_argument("--minio-secure",   action="store_true")
    ap.add_argument("--run-id", default=None, help="תיקיית הריצה ב-MinIO (ברירת מחדל: YYYY/MM/DD/HHmm)")

    args = ap.parse_args()
    run_id = args.run_id or datetime.now().strftime("%Y/%m/%d/%H%M")
    run_crop(
        inp=Path(args.input), out_dir=Path(args.out),
        size=args.size, margin=args.margin, min_wh=args.min_wh,
        orig_dir=Path(args.orig) if args.orig else None, flat=args.flat,
        minio_endpoint=args.minio_endpoint, minio_access=args.minio_access,
        minio_secret=args.minio_secret, minio_bucket=args.minio_bucket,
        minio_prefix=args.minio_prefix, minio_secure=args.minio_secure,
        run_id=run_id,
    )

   

if __name__ == "__main__":
    main()
