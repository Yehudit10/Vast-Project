import argparse
import io
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Tuple

import torch
import torch.nn.functional as F
from PIL import Image
from dotenv import load_dotenv
from minio import Minio
from minio.deleteobjects import DeleteObject
from time import perf_counter  


from inference.utils_infer import build_infer_transforms, load_model

# Optional: DB logging (graceful if missing)
try:
    from metrics_db.db import insert_inference_log
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False


def make_minio_client(endpoint: str, access_key: str, secret_key: str,
                      secure: bool) -> Minio:
    ep = endpoint.replace("http://", "").replace("https://", "")
    return Minio(ep, access_key=access_key, secret_key=secret_key, secure=secure)


def list_images(client: Minio, bucket: str, prefix: str) -> Iterable[str]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        name = obj.object_name
        if Path(name).suffix.lower() in exts:
            yield name


def load_labels(labels_path: str) -> Tuple[dict, dict]:
    with open(labels_path, "r", encoding="utf-8") as f:
        labels_map = json.load(f)
    if all(isinstance(k, str) for k in labels_map.keys()):
        idx_to_class = {int(v): str(k) for k, v in labels_map.items()}
    else:
        idx_to_class = {int(k): str(v) for k, v in labels_map.items()}
    return labels_map, idx_to_class


def build_cfg(cfg_path: str) -> dict:
    import yaml
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_bytes(model, tfms, idx_to_class: dict, file_bytes: bytes):
    
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    x = tfms(img).unsqueeze(0)
    model.eval()
    with torch.no_grad():
        logits = model(x)
        probs = F.softmax(logits, dim=1)
        score, pred = probs.max(dim=1)
        return idx_to_class[int(pred.item())], float(score.item())


def build_prefix(base_prefix: str, dt: date) -> str:
    yyyy = f"{dt.year:04d}"
    mm = f"{dt.month:02d}"
    dd = f"{dt.day:02d}"
    return f"{base_prefix.strip('/')}/{yyyy}/{mm}/{dd}/"


def build_minio_url(endpoint: str, bucket: str, object_name: str) -> str:
    ep = endpoint if endpoint.startswith("http") else f"http://{endpoint}"
    return f"{ep.rstrip('/')}/{bucket}/{object_name}"


def main():
    load_dotenv()

    p = argparse.ArgumentParser(
        description="Batch inference from MinIO by YYYY/MM/DD folder"
    )
    p.add_argument("--date", type=str, default=date.today().isoformat(),
                   help="YYYY-MM-DD (default: today)")
    p.add_argument("--year", type=int, help="Alternative to --date: year")
    p.add_argument("--month", type=int, help="Alternative to --date: month")
    p.add_argument("--day", type=int, help="Alternative to --date: day")
    p.add_argument("--dry-run", action="store_true",
                   help="Print only, do not write DB")
    p.add_argument("--limit", type=int, default=0,
                   help="Limit number of images (0 = no limit)")
    p.add_argument("--delete-ok", action="store_true",
                   help="Delete images from MinIO after success")
    p.add_argument("--weights", type=str,
                   default=os.getenv("WEIGHTS_PATH", "models/best.pt"))
    p.add_argument("--labels", type=str,
                   default=os.getenv("LABELS_PATH", "models/labels.json"))
    p.add_argument("--cfg", type=str,
                   default=os.getenv("CFG_PATH", "configs/fruit_cls.yaml"))
    args = p.parse_args()

    # Load cfg/model
    cfg = build_cfg(args.cfg)
    res = load_model(args.weights, args.labels,
                     backbone=cfg.get("backbone", "mobilenet_v3_small"))
    model = res[0] if isinstance(res, tuple) else res
    _, idx_to_class = load_labels(args.labels)
    tfms = build_infer_transforms(cfg.get("image_size", 224))

    # MinIO settings (ENV > YAML)
    endpoint = os.getenv("S3_ENDPOINT", cfg["s3"]["endpoint"])
    access_key = os.getenv("S3_ACCESS_KEY", cfg["s3"]["access_key"])
    secret_key = os.getenv("S3_SECRET_KEY", cfg["s3"]["secret_key"])
    secure = str(os.getenv("S3_SECURE", cfg["s3"].get("secure", False))
                 ).lower() == "true"
    bucket = os.getenv("S3_BUCKET", cfg["s3"]["bucket"])
    base_prefix = os.getenv("S3_PREFIX", cfg["s3"].get("base_prefix", "images"))

    # Pick date
    if args.year and args.month and args.day:
        run_date = date(args.year, args.month, args.day)
    else:
        run_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    day_prefix = build_prefix(base_prefix, run_date)
    client = make_minio_client(endpoint, access_key, secret_key, secure)

    print(f"[INFO] s3://{bucket}/{day_prefix} | secure={secure}")
    count, to_delete = 0, []

    for object_name in list_images(client, bucket, day_prefix):
        if args.limit and count >= args.limit:
            break

        # Download
        try:
            resp = client.get_object(bucket, object_name)
            data = resp.read()
            resp.close()
            resp.release_conn()
        except Exception as e:
            print(f"[WARN] download failed: {object_name} | {e}")
            continue

        
        try:
            # Classify

            t0 = perf_counter()
            cls, score = classify_bytes(model, tfms, idx_to_class, data)
            t_ms = (perf_counter() - t0) * 1000.0

            cls, score = classify_bytes(model, tfms, idx_to_class, data)
            print(json.dumps({
                "object": object_name,
                "fruit_type": cls,
                "score": round(score, 4),
            }))

            # DB log
            if DB_AVAILABLE and not args.dry_run and os.getenv("DATABASE_URL"):
                try:
                    image_url = build_minio_url(endpoint, bucket, object_name)
                    insert_inference_log(
                        model_backbone=cfg.get("backbone", "mobilenet_v3_small"),
                        image_size=cfg.get("image_size", 224),
                        fruit_type=str(cls),
                        score=float(score),
                        latency_ms=float(t_ms),              # <<< לא None
                        client_ip=f"minio-batch:{run_date.isoformat()}",
                        error=None,
                        image_url=image_url,
                    )

                except Exception as db_e:
                    print(f"[WARN] DB insert failed: {db_e}")

            # Delete after success if requested
            if args.delete_ok:
                to_delete.append(DeleteObject(object_name))

        except Exception as e:
            print(f"[ERR] classify failed: {object_name} | {e}")

        count += 1

    # Bulk delete
    if to_delete:
        errors = client.remove_objects(bucket, to_delete)
        for err in errors:
            print(f"[WARN] delete failed: {err.object_name}: {err}")

    print(f"[DONE] processed={count} | date={run_date.isoformat()}")


if __name__ == "__main__":
    main()
