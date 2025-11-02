# inference/infer_fruit_defect_minio.py
import os
import io
import json
import time
import sys
import logging
from pathlib import Path
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from minio import Minio
from PIL import Image
import numpy as np

# PyTorch
import torch
from torchvision import transforms

# Optional tqdm
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except Exception:
    TQDM_AVAILABLE = False

# --- קונפיג דרך ENV (ברירות מחדל מותאמות לסטאק שלך) ---
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "localhost:9001")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_SECURE     = os.getenv("MINIO_SECURE", "false").lower() == "true"

BUCKET_INPUT     = os.getenv("MINIO_BUCKET_INPUT",  "imagery")
BUCKET_OUTPUT    = os.getenv("MINIO_BUCKET_OUTPUT", "telemetry")
INPUT_PREFIX     = os.getenv("MINIO_INPUT_PREFIX",  "inputs/batch1/")   # מאיפה לקרוא תמונות
OUTPUT_PREFIX    = os.getenv("MINIO_OUTPUT_PREFIX", "results/batch1/")  # לאן להעלות תוצאות

WEIGHTS_BUCKET   = os.getenv("MINIO_BUCKET_WEIGHTS","imagery")
WEIGHTS_PREFIX   = os.getenv("MINIO_WEIGHTS_PREFIX","models/")
LOCAL_WEIGHTS_TS = os.getenv("MODEL_TS_LOCAL",      "./outputs/fruit_cls_best.ts")
LOCAL_WEIGHTS_PT = os.getenv("MODEL_PT_LOCAL",      "./outputs/fruit_cls_best.pt")

IMG_SIZE         = int(os.getenv("IMG_SIZE", "192"))
THRESHOLD        = float(os.getenv("CLS_THRESHOLD", "0.5"))  # סף בינארי defect/ok

DL_WORKERS       = int(os.getenv("DL_WORKERS", "8"))
BATCH_SIZE       = int(os.getenv("BATCH_SIZE", "8"))
HEARTBEAT_PERIOD = int(os.getenv("HEARTBEAT_PERIOD", "30"))  # שניות

# --- logging config ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("infer_minio")

# --- MinIO client ---
mc = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=MINIO_SECURE)


# ----------------------
# utility / IO helpers
# ----------------------
def ensure_local_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def list_images(bucket: str, prefix: str) -> List[str]:
    allowed = (".jpg",".jpeg",".png",".bmp",".webp",".tif",".tiff")
    keys = []
    for obj in mc.list_objects(bucket, prefix=prefix, recursive=True):
        if getattr(obj, "is_dir", False):
            continue
        name = obj.object_name
        if name.lower().endswith(allowed):
            keys.append(name)
    return keys

def download_object(bucket: str, object_name: str, local_path: Path):
    ensure_local_dir(local_path.parent)
    mc.fget_object(bucket, object_name, str(local_path))

def download_images_parallel(bucket: str, keys: List[str], out_dir: Path, workers: int = 8) -> List[Path]:
    """Download keys to out_dir using threads; returns list of local Paths."""
    ensure_local_dir(out_dir)
    local_paths = []

    log.info(f"Starting download of {len(keys)} images (workers={workers})")
    pbar = tqdm(total=len(keys), desc="downloading", unit="img") if TQDM_AVAILABLE else None

    def _dl(key):
        local = out_dir / Path(key).name
        try:
            mc.fget_object(bucket, key, str(local))
            return local, None
        except Exception as e:
            return local, e

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_dl, k) for k in keys]
        for fut in as_completed(futures):
            local, err = fut.result()
            if err:
                log.warning(f"download failed: {local} -> {err}")
            else:
                local_paths.append(local)
            if pbar:
                pbar.update(1)

    if pbar:
        pbar.close()
    log.info(f"Downloaded {len(local_paths)}/{len(keys)} images")
    local_paths.sort(key=lambda p: p.name.lower())
    return local_paths

def write_heartbeat(work_dir: Path, status: str, extra: dict = None):
    try:
        ensure_local_dir(work_dir)
        hb = {"ts": time.time(), "status": status}
        if extra:
            hb.update(extra)
        (work_dir / "status.json").write_text(json.dumps(hb))
    except Exception as e:
        log.debug(f"heartbeat write failed: {e}")

# ----------------------
# model / preprocess
# ----------------------
def fetch_weights_if_missing() -> Path:
    ts_obj = WEIGHTS_PREFIX + "fruit_cls_best.ts"
    pt_obj = WEIGHTS_PREFIX + "fruit_cls_best.pt"
    ts_local = Path(LOCAL_WEIGHTS_TS)
    pt_local = Path(LOCAL_WEIGHTS_PT)

    if ts_local.exists():
        log.info(f"Found local TorchScript weights: {ts_local}")
        return ts_local
    if pt_local.exists():
        log.info(f"Found local PT weights: {pt_local}")
        return pt_local

    # נעדיף TorchScript
    log.info(f"Attempting to download weights from MinIO: {WEIGHTS_BUCKET}/{ts_obj} or .pt")
    try:
        download_object(WEIGHTS_BUCKET, ts_obj, ts_local)
        log.info(f"Downloaded weights: {ts_local}")
        return ts_local
    except Exception as e:
        log.info(f"TorchScript not found in MinIO ({e}), trying PT fallback...")
    # fallback ל-pt
    download_object(WEIGHTS_BUCKET, pt_obj, pt_local)
    log.info(f"Downloaded PT weights: {pt_local}")
    return pt_local

def load_model(weights_path: Path):
    log.info(f"Loading model from: {weights_path}")
    if weights_path.suffix == ".ts":
        model = torch.jit.load(str(weights_path), map_location="cpu")
    else:
        obj = torch.load(str(weights_path), map_location="cpu")
        if hasattr(obj, "state_dict"):
            model = obj
        elif isinstance(obj, dict):
            raise RuntimeError("Loaded a state_dict dict but no model class is defined here. Please export TorchScript (.ts).")
        else:
            model = obj
    model.eval()
    log.info("Model loaded and set to eval()")
    return model

def get_preprocess():
    return transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225]),
    ])

def infer_single(model, img: Image.Image, preprocess, device="cpu") -> Dict:
    x = preprocess(img.convert("RGB")).unsqueeze(0).to(device)
    t0 = time.perf_counter()
    with torch.no_grad():
        y = model(x)
    dt = (time.perf_counter() - t0) * 1000.0  # ms

    if isinstance(y, (list, tuple)):
        y = y[0]
    if isinstance(y, torch.Tensor):
        y = y.squeeze().detach().cpu()
        prob_defect = torch.sigmoid(y).item() if y.numel()==1 else float(torch.softmax(y, dim=0)[1])
    else:
        prob_defect = float(y)

    status = "defect" if prob_defect >= THRESHOLD else "ok"
    confidence = prob_defect if status=="defect" else 1.0 - prob_defect
    return {"status": status, "prob_defect": prob_defect, "confidence": confidence, "latency_ms_model": dt}


# ----------------------
# main runner
# ----------------------
def run_inference_from_minio() -> Dict:
    work = Path("./work_minio")
    imgs_dir = work / "images"
    ensure_local_dir(imgs_dir)

    # heartbeat: starting
    write_heartbeat(work, "starting")

    # 1) Weights
    log.info("Checking for local weights...")
    write_heartbeat(work, "checking_weights")
    weights_path = fetch_weights_if_missing()
    write_heartbeat(work, "weights_ready", {"weights": str(weights_path)})
    log.info(f"Using weights: {weights_path}")
    sys.stdout.flush()

    # 2) Download images to temp workdir
    log.info("Fetching list of images from MinIO...")
    keys = list_images(BUCKET_INPUT, INPUT_PREFIX)
    log.info(f"Found {len(keys)} image keys under s3://{BUCKET_INPUT}/{INPUT_PREFIX}")
    if not keys:
        write_heartbeat(work, "no_images")
        return {"error": f"no images under s3://{BUCKET_INPUT}/{INPUT_PREFIX}"}

    write_heartbeat(work, "downloading_images", {"count": len(keys)})
    downloaded = download_images_parallel(BUCKET_INPUT, keys, imgs_dir, workers=DL_WORKERS)
    write_heartbeat(work, "downloaded_images", {"downloaded": len(downloaded)})
    sys.stdout.flush()

    # 3) Inference loop (batched, tqdm)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_model(weights_path)
    model = model.to(device)
    preprocess = get_preprocess()

    n_images = len(downloaded)
    if n_images == 0:
        write_heartbeat(work, "no_downloaded_images")
        return {"error": f"no images downloaded from s3://{BUCKET_INPUT}/{INPUT_PREFIX}"}

    log.info(f"Starting inference: {n_images} images | batch_size={BATCH_SIZE} | device={device}")
    write_heartbeat(work, "inferring", {"count": n_images, "batch_size": BATCH_SIZE})
    sys.stdout.flush()

    indices = range(0, n_images, BATCH_SIZE)
    pbar = tqdm(total=n_images, desc="Batches" if TQDM_AVAILABLE else "images", unit="img") if TQDM_AVAILABLE else None

    latencies = []
    results = []

    for start in indices:
        batch_paths = downloaded[start:start + BATCH_SIZE]
        names = []
        tensors = []
        for p in batch_paths:
            img = Image.open(p).convert("RGB")
            x = preprocess(img)
            tensors.append(x)
            names.append(p.name)

        batch = torch.stack(tensors, dim=0).to(device)

        t0 = time.perf_counter()
        with torch.no_grad():
            out_batch = model(batch)
        dt_batch_ms = (time.perf_counter() - t0) * 1000.0
        per_image_ms = dt_batch_ms / float(len(batch_paths))

        if isinstance(out_batch, (list, tuple)):
            out_batch = out_batch[0]
        if isinstance(out_batch, torch.Tensor):
            out_cpu = out_batch.detach().cpu()
            for j in range(out_cpu.shape[0]):
                y = out_cpu[j]
                if y.numel() == 1:
                    prob_defect = torch.sigmoid(y).item()
                else:
                    probs = torch.softmax(y, dim=0)
                    prob_defect = float(probs[1]) if probs.numel() > 1 else float(probs[0])
                status = "defect" if prob_defect >= THRESHOLD else "ok"
                confidence = prob_defect if status == "defect" else 1.0 - prob_defect
                latencies.append(per_image_ms)
                results.append({
                    "image": names[j],
                    "status": status,
                    "prob_defect": prob_defect,
                    "confidence": confidence,
                    "latency_ms_model": round(per_image_ms, 3),
                })
        else:
            for j, nm in enumerate(names):
                prob_defect = float(out_batch) if isinstance(out_batch, (float, int)) else 0.0
                status = "defect" if prob_defect >= THRESHOLD else "ok"
                confidence = prob_defect if status == "defect" else 1.0 - prob_defect
                latencies.append(per_image_ms)
                results.append({
                    "image": nm,
                    "status": status,
                    "prob_defect": prob_defect,
                    "confidence": confidence,
                    "latency_ms_model": round(per_image_ms, 3),
                })

        if pbar:
            pbar.update(len(batch_paths))

        # heartbeat update per batch
        if (start // BATCH_SIZE) % 10 == 0:
            write_heartbeat(work, "inferring_in_progress", {"processed": min(start + BATCH_SIZE, n_images), "total": n_images})

    if pbar:
        pbar.close()

    # compute stats
    if latencies:
        p50 = float(np.percentile(latencies, 50))
        p90 = float(np.percentile(latencies, 90))
        p95 = float(np.percentile(latencies, 95))
    else:
        p50 = p90 = p95 = 0.0

    summary = {
        "count": len(results),
        "p50_ms": round(p50,2),
        "p90_ms": round(p90,2),
        "p95_ms": round(p95,2),
        "weights_path": str(weights_path),
        "input_bucket": BUCKET_INPUT,
        "input_prefix": INPUT_PREFIX,
        "output_bucket": BUCKET_OUTPUT,
        "output_prefix": OUTPUT_PREFIX,
        "threshold": THRESHOLD,
        "device": device,
        "batch_size": BATCH_SIZE,
    }

    payload = {"summary": summary, "results": results}

    # 4) Upload results.json back to MinIO (telemetry)
    out_json = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    obj_name = (OUTPUT_PREFIX.rstrip("/") + "/results.json")
    mc.put_object(BUCKET_OUTPUT, obj_name, io.BytesIO(out_json), length=len(out_json), content_type="application/json")
    log.info(f"Uploaded results to {BUCKET_OUTPUT}/{obj_name}")

    try:
        from db_writer import write_results_to_db
        write_results_to_db(payload)
        log.info("Results written to Postgres successfully")
    except Exception as e:
        log.warning(f"Failed to write results to DB: {e}")

    write_heartbeat(work, "done", {"summary": summary})
    return summary


if __name__ == "__main__":
    try:
        s = run_inference_from_minio()
        print(json.dumps(s, indent=2, ensure_ascii=False))
    except Exception as e:
        log.exception("Fatal error during inference")
        # write heartbeat error
        try:
            write_heartbeat(Path("./work_minio"), "error", {"error": str(e)})
        except Exception:
            pass
        raise
