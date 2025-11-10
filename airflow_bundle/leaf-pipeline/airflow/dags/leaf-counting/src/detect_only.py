from __future__ import annotations
import json, argparse
from pathlib import Path
from typing import Optional
from datetime import datetime

import cv2
from ultralytics import YOLO
from common import iter_images, ensure_dir, draw_boxes

try:
    from minio_io import get_client, ensure_bucket, put_png, put_json
except Exception:
    get_client = ensure_bucket = put_png = put_json = None

# def run_detect(inp: Path, out_dir: Path, weights: Path,
#                conf: float=0.25, imgsz: int=896, device: str="cpu",
#                minio_endpoint: Optional[str]=None, minio_access: Optional[str]=None,
#                minio_secret: Optional[str]=None, minio_bucket: Optional[str]=None,
#                minio_prefix: str="detect", minio_secure: bool=False):
#     out_dir = ensure_dir(out_dir)
#     overlay_dir = ensure_dir(out_dir / "overlay")
#     json_dir = ensure_dir(out_dir / "json")

#     cli = None
#     if minio_endpoint and minio_access and minio_secret and minio_bucket:
#         if get_client is None:
#             raise SystemExit("[ERR] חסר minio או minio_io.")
#         cli = get_client(minio_endpoint, minio_access, minio_secret, secure=minio_secure)
#         ensure_bucket(cli, minio_bucket)

#     model = YOLO(str(weights))
#     img_paths = list(iter_images(inp))
#     if not img_paths:
#         raise SystemExit(f"[ERR] No images found under: {inp}")

#     for img_path in img_paths:
#         img_bgr = cv2.imread(str(img_path))
#         if img_bgr is None:
#             print(f"[WARN] can't read image: {img_path}")
#             continue
#         h, w = img_bgr.shape[:2]
#         res = model.predict(source=img_bgr, conf=conf, imgsz=imgsz, device=device, verbose=False)[0]

#         boxes_pix = []
#         if res.boxes is not None and len(res.boxes) > 0:
#             for b in res.boxes:
#                 xyxy = b.xyxy.cpu().numpy().reshape(-1)
#                 conf_i = float(b.conf.cpu().numpy().reshape(-1)[0])
#                 cls_i  = float(b.cls.cpu().numpy().reshape(-1)[0]) if b.cls is not None else 0.0
#                 x1,y1,x2,y2 = map(float, xyxy.tolist())
#                 boxes_pix.append([x1,y1,x2,y2,conf_i,cls_i])

#         j = {
#             "image": img_path.name,
#             "source_path": str(img_path.resolve()),  # <<< חדש: מקור התמונה המלא
#             "width": w, "height": h,
#             "boxes": boxes_pix
#         }
#         json_path = json_dir / (img_path.stem + ".json")
#         json_path.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")

#         overlay = draw_boxes(img_bgr, boxes_pix)
#         overlay_path = overlay_dir / img_path.name
#         cv2.imwrite(str(overlay_path), overlay)

#         if cli:
#             put_json(cli, minio_bucket, f"{minio_prefix}/json/{img_path.stem}.json", j)
#             put_png(cli,  minio_bucket, f"{minio_prefix}/overlay/{img_path.stem}.png", overlay)

#         print(f"[OK] {img_path.name} -> {json_path.name}, boxes={len(boxes_pix)}")
# def run_detect(inp: Path, out_dir: Path, weights: Path,
#                conf: float=0.25, imgsz: int=896, device: str="cpu",
#                minio_endpoint: Optional[str]=None, minio_access: Optional[str]=None,
#                minio_secret: Optional[str]=None, minio_bucket: Optional[str]=None,
#                minio_prefix: str="detect", minio_secure: bool=False,
#                run_id: Optional[str]=None):
def run_detect(inp: Path, out_dir: Path, weights: Path,
               conf: float=0.25, imgsz: int=896, device: str="cpu",
               minio_endpoint: Optional[str]=None, minio_access: Optional[str]=None,
               minio_secret: Optional[str]=None, minio_bucket: Optional[str]=None,
               minio_prefix: str="DETECT", minio_secure: bool=False,
               run_id: Optional[str]=None):

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

    # איסוף תמונות
    img_paths = list(iter_images(inp))
    if not img_paths:
        raise SystemExit(f"[ERR] No images found under: {inp}")

    is_dir_input = Path(inp).is_dir()

    for img_path in img_paths:
        # יחסית לשורש הקלט (אם תיקייה)
        rel_path = img_path.name if not is_dir_input else str(img_path.relative_to(inp))
        rel_parent = "." if not is_dir_input else str(img_path.relative_to(inp).parent)
        rel_stem = Path(rel_path).stem

        # תיקיות פלט משוקפות
        overlay_dir = ensure_dir(overlay_root / rel_parent)
        json_dir = ensure_dir(json_root / rel_parent)

        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            print(f"[WARN] can't read image: {img_path}")
            continue
        h, w = img_bgr.shape[:2]

        res = model.predict(source=img_bgr, conf=conf, imgsz=imgsz, device=device, verbose=False)[0]

        boxes_pix = []
        if res.boxes is not None and len(res.boxes) > 0:
            for b in res.boxes:
                xyxy = b.xyxy.cpu().numpy().reshape(-1)
                conf_i = float(b.conf.cpu().numpy().reshape(-1)[0])
                cls_i  = float(b.cls.cpu().numpy().reshape(-1)[0]) if b.cls is not None else 0.0
                x1,y1,x2,y2 = map(float, xyxy.tolist())
                boxes_pix.append([x1,y1,x2,y2,conf_i,cls_i])

        j = {
            "image": img_path.name,
            "rel_path": rel_path,                # <<< חדש: הנתיב היחסי בקלט
            "source_path": str(img_path.resolve()),
            "width": w, "height": h,
            "boxes": boxes_pix
        }
        json_path = json_dir / f"{rel_stem}.json"
        json_path.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")

        overlay = draw_boxes(img_bgr, boxes_pix)
        ov_path = overlay_dir / img_path.name
        cv2.imwrite(str(ov_path), overlay)

        if cli:
            # minio_json_key = f"{minio_prefix}/json/{rel_parent}/{rel_stem}.json" if rel_parent != "." else f"{minio_prefix}/json/{rel_stem}.json"
            # minio_ov_key   = f"{minio_prefix}/overlay/{rel_parent}/{img_path.name}" if rel_parent != "." else f"{minio_prefix}/overlay/{img_path.name}"
            # put_json(cli, minio_bucket, minio_json_key, j)
            # put_png(cli,  minio_bucket, minio_ov_key, overlay)
            base = f"{run_id}/{minio_prefix}"  # תאריך/שעה קודם, אח"כ DETECT
            minio_json_key = f"{base}/json/{rel_parent}/{rel_stem}.json" if rel_parent != "." else f"{base}/json/{rel_stem}.json"
            minio_ov_key   = f"{base}/overlay/{rel_parent}/{img_path.name}" if rel_parent != "." else f"{base}/overlay/{img_path.name}"
            put_json(cli, minio_bucket, minio_json_key, j)
            put_png(cli,  minio_bucket, minio_ov_key, overlay)

        print(f"[OK] {rel_path} -> {json_path.relative_to(out_dir)}, boxes={len(boxes_pix)}")

def main():
    ap = argparse.ArgumentParser(description="YOLO detect -> pixel JSON + overlay (+optional MinIO)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--imgsz", type=int, default=896)
    ap.add_argument("--device", default="cpu")

    ap.add_argument("--minio-endpoint", default=None)
    ap.add_argument("--minio-access",   default=None)
    ap.add_argument("--minio-secret",   default=None)
    ap.add_argument("--minio-bucket",   default=None)
    ap.add_argument("--minio-prefix",   default="detect")
    ap.add_argument("--minio-secure",   action="store_true")
    ap.add_argument("--run-id", default=None, help="תיקיית הריצה ב-MinIO (ברירת מחדל: YYYY/MM/DD/HHmm)")

    args = ap.parse_args()
    # run_detect(Path(args.input), Path(args.out), Path(args.weights),
    #            conf=args.conf, imgsz=args.imgsz, device=args.device,
    #            minio_endpoint=args.minio_endpoint, minio_access=args.minio_access,
    #            minio_secret=args.minio_secret, minio_bucket=args.minio_bucket,
    #            minio_prefix=args.minio_prefix, minio_secure=args.minio_secure)
    run_id = args.run_id or datetime.now().strftime("%Y/%m/%d/%H%M")
    run_detect(Path(args.input), Path(args.out), Path(args.weights),
           conf=args.conf, imgsz=args.imgsz, device=args.device,
           minio_endpoint=args.minio_endpoint, minio_access=args.minio_access,
           minio_secret=args.minio_secret, minio_bucket=args.minio_bucket,
           minio_prefix=args.minio_prefix, minio_secure=args.minio_secure,
           run_id=run_id)

if __name__ == "__main__":
    main()
