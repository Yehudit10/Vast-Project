import io, json, math, random, argparse
from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
import cv2 as cv
from minio import Minio
from sklearn.metrics import f1_score
import argparse
from segment import segment_fruit
from heuristics import compute_features  

LABELS = ["unripe", "ripe", "overripe"]
L2I = {l:i for i,l in enumerate(LABELS)}

@dataclass
class Feat:
    mean_h: float
    mean_s: float
    mean_v: float
    brown_ratio: float

def _to_bgr(img_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv.imdecode(arr, cv.IMREAD_COLOR)
    if img is None:
        raise ValueError("failed to decode image")
    return img

def _white_balance_and_clahe(img: np.ndarray) -> np.ndarray:
    imgf = img.astype(np.float32)
    m = imgf.mean()
    for c in range(3):
        imgf[..., c] *= m / (imgf[..., c].mean() + 1e-6)
    imgf = np.clip(imgf, 0, 255).astype(np.uint8)
    lab = cv.cvtColor(imgf, cv.COLOR_BGR2LAB)
    l, a, b = cv.split(lab)
    clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv.cvtColor(cv.merge([l, a, b]), cv.COLOR_LAB2BGR)


def extract_features(img: np.ndarray) -> Feat:
    img = _white_balance_and_clahe(img)
    mask,_ = segment_fruit(img, fruit=args.fruit)
    hsv = cv.cvtColor(img, cv.COLOR_BGR2HSV)
    H,S,V = hsv[...,0][mask], hsv[...,1][mask], hsv[...,2][mask]
    if H.size == 0:
        return Feat(0,0,0,0)
    brown_h = ((H>=5)&(H<=25))
    brown_vs = ((V<=90)&(S>=60))
    brown = (brown_h | brown_vs)
    return Feat(float(H.mean()), float(S.mean()), float(V.mean()),
                float(brown.mean()))

def classify(feat: Feat, thr: Dict[str,float]) -> str:
    hmin = float(thr.get("unripe_h_min", 30))
    hmax = float(thr.get("unripe_h_max", 95))
    min_s = float(thr.get("unripe_min_s", 25))
    br_th = float(thr.get("overripe_brown_ratio", 0.12))
    v_dark = float(thr.get("overripe_min_v", 55))

    if feat.brown_ratio >= br_th or (feat.brown_ratio >= br_th*0.7 and feat.mean_v <= v_dark and not (hmin <= feat.mean_h <= hmax)):
        return "overripe"
    if (hmin <= feat.mean_h <= hmax) and (feat.mean_s >= min_s):
        return "unripe"
    return "ripe"

def load_minio(minio_url, ak, sk, bucket, prefix,fruit, limit=None) -> List[Tuple[Feat,int]]:
    mc = Minio(minio_url.replace("http://","").replace("https://",""),
               access_key=ak, secret_key=sk,
               secure=minio_url.startswith("https"))
    objects = mc.list_objects(bucket, prefix=prefix, recursive=True)
    out = []
    for i,obj in enumerate(objects):
        if limit and i>=limit: break
        name = obj.object_name.lower()
        if not (name.endswith(".jpg") or name.endswith(".jpeg") or name.endswith(".png")):
            continue
        data = mc.get_object(bucket, obj.object_name).read()
        img = _to_bgr(data)
        mask, _ = segment_fruit(img, fruit=fruit)
        feat = compute_features(img, mask)
        if "/unripe" in name: y=L2I["unripe"]
        elif "/ripe" in name: y=L2I["ripe"]
        elif "/overripe" in name: y=L2I["overripe"]
        else:                   continue
        out.append((feat,y))
    return out

def score(features: List[Feat], y: np.ndarray, thr: Dict[str,float]) -> float:
    preds = np.array([L2I[classify(f, thr)] for f,_ in zip(features,y)])
    f1 = f1_score(y, preds, average="macro")

    penalty = np.mean((y==L2I["unripe"]) & (preds==L2I["overripe"]))
    return float(f1 - 0.5*penalty)

SEARCH_SPACE = {
    "unripe_h_min": (25, 40),
    "unripe_h_max": (85, 100),
    "unripe_min_s": (15, 35),
    "overripe_brown_ratio": (0.08, 0.2),
    "overripe_min_v": (45, 70),
}

def sample(thr0: Dict[str,float]) -> Dict[str,float]:
    t = dict(thr0)
    for k,(lo,hi) in SEARCH_SPACE.items():
        t[k] = random.uniform(lo, hi)
    return t

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minio-url", required=True)
    ap.add_argument("--access-key", required=True)
    ap.add_argument("--secret-key", required=True)
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--prefix", required=True)     
    ap.add_argument("--fruit", required=True, choices=["apple","banana","orange"])
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default="./thresholds.json")
    args = ap.parse_args()

    print("[tune] loading data from MinIO…")
    data = load_minio(args.minio_url, args.access_key, args.secret_key,
                      args.bucket, args.prefix,args.fruit, limit=args.limit)
    feats, y = zip(*data)
    y = np.array(y)

    random.seed(42)
    best_thr = {k:np.mean(v) if isinstance(v, tuple) else v for k,v in SEARCH_SPACE.items()}
    best = -1.0
    for i in range(1, args.iters+1):
        thr = sample(best_thr)
        s = score(feats, y, thr)
        if s > best:
            best, best_thr = s, thr
        if i % 25 == 0:
            print(f"[tune] {i:4d}/{args.iters}  best_score={best:.4f}  best={best_thr}")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(best_thr, f, indent=2)
    print(f"[tune] DONE. wrote: {args.out}")

if __name__ == "__main__":
    main()
