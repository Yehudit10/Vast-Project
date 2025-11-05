# file: services/weekly_ripeness_job.py
import io
import time
import torch
import psycopg2
import datetime as dt
from urllib.parse import urlparse
from minio import Minio
from PIL import Image
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))  # so "models" is importable
from models.mobilenet_v3_large_head import build_conditional
from tqdm.auto import tqdm


from pathlib import Path
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parents[1] / ".env"  
    if env_path.exists():
        load_dotenv(env_path.as_posix())
except Exception:
    pass

# ---- ENV ----
PGHOST = os.getenv("PGHOST", "db")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE", "missions_db")
PGUSER = os.getenv("PGUSER", "missions_user")
PGPASSWORD = os.getenv("PGPASSWORD", "pg123")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

MODEL_PATH = os.getenv("MODEL_PATH", "/models/best_conditional.pt")
MODEL_NAME = os.getenv("MODEL_NAME", "best_conditional")
BATCH_LIMIT = int(os.getenv("BATCH_LIMIT", "200"))

# ----- labels & fruits mapping -----
LABELS = ["unripe", "ripe", "overripe"]  
FRUITS = ["Apple", "Banana", "Orange", "."]   
FRUIT2IDX = {name.lower(): i for i, name in enumerate(FRUITS)}

# ----- build model & load weights -----
device = "cuda" if torch.cuda.is_available() else "cpu"
num_ripeness = len(LABELS)
num_fruits = len(FRUITS)

model = build_conditional(num_ripeness=num_ripeness, num_fruits=num_fruits, embed_dim=16).to(device)

ckpt = torch.load(MODEL_PATH, map_location=device)
state = ckpt["state_dict"] if (isinstance(ckpt, dict) and "state_dict" in ckpt) else ckpt

assert state["fruit_embed.weight"].shape[0] == num_fruits, \
    f"Checkpoint expects {state['fruit_embed.weight'].shape[0]} fruits, but FRUITS has {num_fruits}"

model.load_state_dict(state, strict=True)
model.eval()

def load_image_for_model(img_bytes):
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    from torchvision import transforms
    preprocess = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])
    ])
    return preprocess(im).unsqueeze(0).to(device)

@torch.no_grad()
def predict_ripeness(img_tensor, fruit_type: str):
    idx = FRUIT2IDX.get(fruit_type.lower())
    if idx is None:
        raise KeyError(f"skip: fruit '{fruit_type}' not in trained set {FRUITS}")
    fruit_idx_tensor = torch.tensor([idx], dtype=torch.long, device=device)
    logits = model(img_tensor, fruit_idx_tensor)
    probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()
    j = int(probs.argmax())
    return LABELS[j], float(probs[j])

# ---- MINIO ----
minio_client = Minio(MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, secure=MINIO_SECURE)

def fetch_from_minio(image_url: str) -> bytes:
    p = urlparse(image_url)
    path = p.path.lstrip("/")
    bucket, *rest = path.split("/", 1)
    if not rest:
        raise ValueError(f"Invalid URL path for MinIO: {image_url}")
    obj = rest[0]
    resp = minio_client.get_object(bucket, obj)
    data = resp.read()
    resp.close()
    resp.release_conn()
    return data

# ---- DB ----
def get_conn():
    return psycopg2.connect(
        host=PGHOST, port=PGPORT, dbname=PGDATABASE, user=PGUSER, password=PGPASSWORD
    )

def main():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
        SELECT il.id, il.ts, il.fruit_type, il.image_url
        FROM inference_logs il
        LEFT JOIN ripeness_predictions rp ON rp.inference_log_id = il.id
        WHERE il.ts >= now() - interval '7 days'
          AND rp.id IS NULL
        ORDER BY il.id ASC
        LIMIT %s;
        """, (BATCH_LIMIT,))
        rows = cur.fetchall()

    processed = 0

    # generate a single run_id for this batch
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT gen_random_uuid()")
        run_id = cur.fetchone()[0]

    for inflog_id, ts, fruit_type, image_url in tqdm(rows, desc="Predicting ripeness"):
        try:
            if processed % 20 == 0:
                print(f"...processed {processed} so far")
            img_bytes = fetch_from_minio(image_url)
            tensor = load_image_for_model(img_bytes)
            try:
                label, score = predict_ripeness(tensor, fruit_type)
            except KeyError as skip:
                print(f"[SKIP] inflog_id={inflog_id} :: {skip}")
                continue

            # derive bucket/object_key and lookup device_id
            device_id = None
            try:
                p = urlparse(image_url)
                path = p.path.lstrip('/')
                if '/' in path:
                    bucket, object_key = path.split('/', 1)
                    with get_conn() as conn, conn.cursor() as cur:
                        cur.execute("SELECT device_id FROM files WHERE bucket = %s AND object_key = %s", (bucket, object_key))
                        res = cur.fetchone()
                        device_id = res[0] if res else None
            except Exception:
                # keep device_id as None if parsing/lookup fails
                device_id = None

            with get_conn() as conn, conn.cursor() as cur:
                cur.execute("""
                INSERT INTO ripeness_predictions
                    (inference_log_id, ts, ripeness_label, ripeness_score, model_name, run_id, device_id)
                VALUES (%s, now(), %s, %s, %s, %s, %s)
                ON CONFLICT (inference_log_id) DO NOTHING;
                """, (inflog_id, label, score, MODEL_NAME, run_id, device_id))
            processed += 1
            print(f"[OK] inflog_id={inflog_id} -> {label} ({score:.4f})")
        except Exception as e:
            print(f"[ERR] inflog_id={inflog_id} url={image_url} :: {e}")

    print(f"Done. processed={processed}")

if __name__ == "__main__":
    main()
