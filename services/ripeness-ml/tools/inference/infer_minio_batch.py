# AGCLOUD/services/ripeness-ml/scripts/infer_minio_batch.py
import argparse, os, sys, csv, json
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
from minio import Minio
from tqdm import tqdm
import onnxruntime as ort
from torchvision import transforms

# ---- Configurable defaults ----
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD  = (0.229, 0.224, 0.225)
IMG_TFM = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
])

DEFAULT_FRUITS = ["apple", "banana", "orange", "pineapple"]  # order matters!
RIPENESS = ["unripe", "ripe", "overripe"]

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")


def parse_args():
    p = argparse.ArgumentParser(
        description="Batch inference from MinIO prefix with conditional ONNX model (image + fruit_idx)."
    )
    p.add_argument("--minio-url", required=True, help="http://127.0.0.1:9001")
    p.add_argument("--access-key", default=os.getenv("MINIO_ACCESS_KEY", "minioadmin"))
    p.add_argument("--secret-key", default=os.getenv("MINIO_SECRET_KEY", "minioadmin"))
    p.add_argument("--secure", action="store_true", help="Use HTTPS")

    p.add_argument("--bucket", required=True, help="MinIO bucket name")
    p.add_argument("--prefix", help="Prefix to scan, e.g. samples/2025/10/15 (ignored if --pairs-csv is used)")

    p.add_argument("--onnx", default="ripeness_conditional.onnx", help="Path to conditional ONNX model")
    p.add_argument("--providers", nargs="*", default=None, help="ONNX Runtime providers list (default: CPU)")

    # Fruit specification
    p.add_argument("--fruit", help="Fruit for ALL objects (apple|banana|orange|pineapple)")
    p.add_argument("--pairs-csv", help="CSV file with columns: object,fruit (mapping per object)")

    # Fruits list order (so fruit_idx matches training)
    p.add_argument("--fruits", default=None,
                   help='Fruits list in order, e.g. \'["apple","banana","orange","pineapple"]\' or "apple,banana,orange,pineapple"')

    # Output
    p.add_argument("--out-csv", help="Optional: write results to CSV (object,fruit,label,prob_unripe,prob_ripe,prob_overripe)")
    p.add_argument("--quiet", action="store_true", help="Do not print JSON lines to stdout")

    args = p.parse_args()

    if not args.pairs_csv and not (args.prefix and args.fruit):
        p.error("Provide either --pairs-csv OR both --prefix and --fruit.")

    return args


def parse_fruits_list(fruits_arg):
    if not fruits_arg:
        return DEFAULT_FRUITS
    s = fruits_arg.strip()
    if s.startswith("["):
        # JSON-ish
        try:
            import json as _json
            lst = _json.loads(s)
            return [x.strip().lower() for x in lst]
        except Exception:
            pass
    # comma separated
    return [x.strip().lower() for x in s.split(",") if x.strip()]


def softmax(x):
    x = x - x.max(axis=1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=1, keepdims=True)


def is_image(name: str) -> bool:
    return name.lower().endswith(IMG_EXTS)


def load_pairs_csv(path: str):
    mapping = {}
    with open(path, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if "object" not in r.fieldnames or "fruit" not in r.fieldnames:
            raise SystemExit("pairs CSV must have columns: object,fruit")
        for row in r:
            obj = row["object"].strip()
            fruit = row["fruit"].strip().lower()
            mapping[obj] = fruit
    return mapping


def open_minio(args):
    secure = args.secure or args.minio_url.startswith("https://")
    endpoint = args.minio_url.replace("http://", "").replace("https://", "")
    return Minio(endpoint, access_key=args.access_key, secret_key=args.secret_key, secure=secure)


def main():
    args = parse_args()
    fruits = parse_fruits_list(args.fruits)

    # Validate fruit names
    fruit_set = set(fruits)

    # Prepare ONNX Runtime session
    providers = args.providers or ["CPUExecutionProvider"]
    sess = ort.InferenceSession(args.onnx, providers=providers)

    client = open_minio(args)

    # Prepare iterator over (object_name, fruit)
    if args.pairs_csv:
        mapping = load_pairs_csv(args.pairs_csv)
        # Only iterate the keys present in the CSV (no MinIO list needed)
        iterator = [(obj, mapping[obj]) for obj in mapping]
    else:
        fixed_fruit = args.fruit.lower()
        if fixed_fruit not in fruit_set:
            raise SystemExit(f"--fruit must be one of {fruits}; got {fixed_fruit}")
        iterator = []
        for obj in client.list_objects(args.bucket, prefix=args.prefix, recursive=True):
            if is_image(obj.object_name):
                iterator.append((obj.object_name, fixed_fruit))

    # Output CSV writer (optional)
    csv_writer = None
    if args.out_csv:
        Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
        fcsv = open(args.out_csv, "w", newline="", encoding="utf-8")
        csv_writer = csv.writer(fcsv)
        csv_writer.writerow(["object", "fruit", "label", "prob_unripe", "prob_ripe", "prob_overripe"])

    # Run predictions
    for obj_name, fruit in tqdm(iterator, desc="Predicting"):
        if fruit not in fruit_set:
            # Unknown fruit -> skip
            if not args.quiet:
                print(json.dumps({"object": obj_name, "error": f"unknown fruit '{fruit}' (allowed {fruits})"}, ensure_ascii=False))
            continue

        # Fetch image bytes
        if args.pairs_csv:
            # object names in CSV must be full paths in bucket
            resp = client.get_object(args.bucket, obj_name)
        else:
            resp = client.get_object(args.bucket, obj_name)

        try:
            img = Image.open(BytesIO(resp.read())).convert("RGB")
        finally:
            resp.close(); resp.release_conn()

        x = IMG_TFM(img).unsqueeze(0).numpy()
        fidx = np.array([fruits.index(fruit)], dtype=np.int64)

        logits = sess.run(["ripeness_logits"], {"images": x, "fruit_idx": fidx})[0]
        prob = softmax(logits)[0]
        idx = int(prob.argmax())
        label = RIPENESS[idx]

        record = {
            "object": obj_name,
            "fruit": fruit,
            "label": label,
            "probs": {RIPENESS[i]: float(prob[i]) for i in range(len(RIPENESS))}
        }

        if not args.quiet:
            print(json.dumps(record, ensure_ascii=False))

        if csv_writer:
            csv_writer.writerow([
                obj_name, fruit, label,
                f"{prob[0]:.6f}", f"{prob[1]:.6f}", f"{prob[2]:.6f}"
            ])

    if csv_writer:
        fcsv.close()


if __name__ == "__main__":
    main()
