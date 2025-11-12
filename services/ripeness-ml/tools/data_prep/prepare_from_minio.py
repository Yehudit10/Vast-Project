# AGCLOUD/services/ripeness-ml/scripts/prepare_from_minio.py
import os, io, csv, argparse, sys, re, datetime as dt
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from minio import Minio
from minio.error import S3Error
from tqdm import tqdm
import random

def parse_args():
    p = argparse.ArgumentParser(description="Sync labeled images from MinIO into local data/train|val|test/<class>")
    p.add_argument("--minio-url", required=True, help="e.g. http://127.0.0.1:9000")
    p.add_argument("--access-key", required=False, default=os.getenv("MINIO_ACCESS_KEY","minioadmin"))
    p.add_argument("--secret-key", required=False, default=os.getenv("MINIO_SECRET_KEY","minioadmin"))
    p.add_argument("--secure", action="store_true", help="use HTTPS")
    p.add_argument("--bucket", required=True, help="e.g. classification")
    p.add_argument("--prefix", required=True, help="e.g. samples/2025/ or samples/")
    p.add_argument("--outdir", default="data", help="local output root")
    p.add_argument("--split", default="0.7,0.15,0.15", help="train,val,test ratios")
    p.add_argument("--labels-csv", help="path to labels.csv (local file) OR object path in bucket (starts without leading /)")
    p.add_argument("--infer-label-from-folder", action="store_true", help="take class name from folder under prefix")
    p.add_argument("--from-date", help="YYYY-MM-DD (inclusive)")
    p.add_argument("--to-date", help="YYYY-MM-DD (inclusive)")
    p.add_argument("--last-days", type=int, help="Use only last N days under prefix (overrides from/to)")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()

def list_objects(client: Minio, bucket: str, prefix: str):
    return client.list_objects(bucket, prefix=prefix, recursive=True)

DATE_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})(?:/|$)")

def object_date(obj_name: str) -> Optional[dt.date]:
    m = DATE_RE.search("/"+obj_name.strip("/"))
    if not m: return None
    y, mth, d = map(int, m.groups())
    return dt.date(y, mth, d)

def load_labels_from_csv_local(csv_path: str) -> Dict[str, str]:
    mapping = {}
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            mapping[row["object"].strip()] = row["label"].strip()
    return mapping

def load_labels_from_csv_minio(client: Minio, bucket: str, obj_path: str) -> Dict[str, str]:
    resp = client.get_object(bucket, obj_path)
    data = resp.read().decode("utf-8")
    mapping = {}
    for row in csv.DictReader(io.StringIO(data)):
        mapping[row["object"].strip()] = row["label"].strip()
    return mapping

def ensure_dirs(root: Path, classes: List[str]):
    for split in ["train","val","test"]:
        for c in classes:
            (root/split/c).mkdir(parents=True, exist_ok=True)

def main():
    args = parse_args()
    tr, va, te = [float(x) for x in args.split.split(",")]
    assert abs(tr+va+te - 1.0) < 1e-6, "--split must sum to 1.0"

    secure = args.secure or args.minio_url.startswith("https://")
    endpoint = args.minio_url.replace("http://","").replace("https://","")
    client = Minio(endpoint, access_key=args.access_key, secret_key=args.secret_key, secure=secure)

    # python arg names can't contain hyphen; fallback
    access = getattr(args, "access_key", getattr(args, "access-key", None))
    secret = getattr(args, "secret_key", getattr(args, "secret-key", None))
    client = Minio(endpoint, access_key=access, secret_key=secret, secure=secure)

    # gather all candidate objects under prefix
    objs = list(list_objects(client, args.bucket, args.prefix))
    if len(objs)==0:
        print("No objects under prefix:", args.prefix); sys.exit(1)

    # filter by date
    if args.last_days:
        cutoff = dt.date.today() - dt.timedelta(days=args.last_days)
        objs = [o for o in objs if (object_date(o.object_name) or dt.date.min) >= cutoff]
    else:
        dfrom = dt.date.fromisoformat(args.from_date) if args.from_date else None
        dto   = dt.date.fromisoformat(args.to_date)   if args.to_date else None
        if dfrom or dto:
            def inrange(o):
                od = object_date(o.object_name)
                if not od: return False
                if dfrom and od < dfrom: return False
                if dto and od > dto: return False
                return True
            objs = [o for o in objs if inrange(o)]

    # Build label mapping
    label_map: Dict[str,str] = {}
    classes: set = set()

    if args.labels_csv:
        if os.path.exists(args.labels_csv):
            label_map = load_labels_from_csv_local(args.labels_csv)
        else:
            label_map = load_labels_from_csv_minio(client, args.bucket, args.labels_csv)
        classes = set(label_map.values())
        candidates = [(o.object_name, label_map.get(o.object_name)) for o in objs if o.object_name in label_map]
    elif args.infer_label_from_folder:
        # Expect .../<class>/... somewhere AFTER prefix
        pref = args.prefix.strip("/")
        candidates = []
        for o in objs:
            rel = o.object_name[len(pref):].strip("/")
            parts = rel.split("/")
            if len(parts)>=2:
                cls = parts[0]
                candidates.append((o.object_name, cls))
                classes.add(cls)
        if not classes:
            print("Could not infer classes from folders; provide --labels-csv", file=sys.stderr)
            sys.exit(2)
    else:
        print("Provide either --labels-csv or --infer-label-from-folder", file=sys.stderr)
        sys.exit(2)

    classes = sorted(list(classes))
    print("Classes:", classes, "| samples:", len(candidates))
    root = Path(args.outdir)
    ensure_dirs(root, classes)

    # stratified split by class
    by_cls: Dict[str, List[str]] = {c: [] for c in classes}
    for obj, lab in candidates:
        if lab in by_cls:
            by_cls[lab].append(obj)
    for c in classes: random.shuffle(by_cls[c])

    plan: List[Tuple[str, str]] = []  # (object_name, target_path)
    for c in classes:
        items = by_cls[c]
        n = len(items); ntr = int(tr*n); nv = int(va*n)
        tr_items = items[:ntr]; va_items = items[ntr:ntr+nv]; te_items = items[ntr+nv:]
        for src in tr_items:
            plan.append((src, str(root/ "train"/c/ Path(src).name)))
        for src in va_items:
            plan.append((src, str(root/ "val"/c/ Path(src).name)))
        for src in te_items:
            plan.append((src, str(root/ "test"/c/ Path(src).name)))

    if args.dry_run:
        print(f"DRY-RUN: would download {len(plan)} files.")
        return

    # download
    for src, dst in tqdm(plan, desc="Downloading"):
        dpath = Path(dst)
        if dpath.exists(): continue
        dpath.parent.mkdir(parents=True, exist_ok=True)
        client.fget_object(args.bucket, src, dst)
    print("Done. Data prepared under:", root.resolve())

if __name__ == "__main__":
    main()
