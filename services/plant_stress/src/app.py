# services/plant_stress/src/app.py

import os, sys, glob, datetime as dt, pickle
from pathlib import Path
from typing import List, Tuple
import numpy as np
import librosa
import tensorflow as tf
import psycopg2
from psycopg2.extras import execute_values

# ← אם את משתמשת בדיווח ל-db_api, הקובץ הזה חייב להיות אצלך:
# services/plant_stress/src/db_api_client.py
# והוא כולל את write_db_entry(meta)
try:
    from db_api_client import write_db_entry  # אופציונלי (ידפיס שגיאה אם אין)
    _HAS_DB_API_CLIENT = True
except Exception as _e:
    print(f"[db_api] client not available: {_e}")
    _HAS_DB_API_CLIENT = False

# ============ ENV / CONFIG ============
INPUT_DIR = os.getenv("INPUT_DIR", "/data/inbox")
MODEL_DIR = os.getenv("MODEL_DIR", "/models")
POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql://postgres:postgres@host.docker.internal:5432/missions_db"
)
PERIOD_DAYS = int(os.getenv("PERIOD_DAYS", "7"))
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.0"))

# דיווח ל-db_api (לא חובה): 1=לשלוח, 0=לא לשלוח
DB_API_REPORT = os.getenv("DB_API_REPORT", "0") == "1"
# שם bucket ל-db_api (כששולחים meta)
DB_API_BUCKET = os.getenv("DB_API_BUCKET", "local-audio")

# ============ Ultrasound constants (2ms @ 500kHz) ============
SAMPLE_RATE = 500_000
DURATION_MS = 2
N_SAMPLES = int(SAMPLE_RATE * DURATION_MS / 1000)  # 1000
N_FFT = 256
HOP_LENGTH = 64
N_MELS = 64

# ============ Audio helpers ============
def load_audio(path: Path):
    audio, sr = librosa.load(str(path), sr=None, mono=True)
    if len(audio) > N_SAMPLES:
        start = (len(audio) - N_SAMPLES) // 2
        audio = audio[start:start + N_SAMPLES]
    elif len(audio) < N_SAMPLES:
        pad = N_SAMPLES - len(audio)
        audio = np.pad(audio, (0, pad))
    return audio.astype(np.float32), (sr or SAMPLE_RATE)

def extract_features(audio: np.ndarray, sr: int) -> np.ndarray:
    feats = []
    feats.extend([np.mean(audio), np.std(audio), np.max(audio), np.min(audio), np.var(audio), np.median(audio)])
    zcr = librosa.feature.zero_crossing_rate(audio, hop_length=HOP_LENGTH)[0]
    feats.extend([np.mean(zcr), np.std(zcr), np.max(zcr)])
    fft = np.abs(np.fft.fft(audio))[: len(audio) // 2]
    feats.extend([np.mean(fft), np.std(fft), np.max(fft), np.argmax(fft)])
    try:
        sc = librosa.feature.spectral_centroid(y=audio, sr=sr, hop_length=HOP_LENGTH, n_fft=N_FFT)[0]
        ro = librosa.feature.spectral_rolloff(y=audio, sr=sr, hop_length=HOP_LENGTH, n_fft=N_FFT)[0]
        feats.extend([np.mean(sc), np.mean(ro)])
    except Exception:
        feats.extend([0.0, 0.0])
    rms = librosa.feature.rms(y=audio, hop_length=HOP_LENGTH, frame_length=N_FFT)[0]
    feats.extend([np.mean(rms), np.std(rms)])
    return np.array(feats, dtype=np.float32)

def create_melspec(audio: np.ndarray, sr: int) -> np.ndarray:
    try:
        mel = librosa.feature.melspectrogram(
            y=audio, sr=sr, n_fft=N_FFT, hop_length=HOP_LENGTH, n_mels=N_MELS, fmax=sr // 2
        )
        db = librosa.power_to_db(mel, ref=np.max)
        norm = (db - db.min()) / (db.max() - db.min() + 1e-8)
        return norm.astype(np.float32)
    except Exception:
        T = max(1, N_SAMPLES // HOP_LENGTH)
        return np.zeros((N_MELS, T), dtype=np.float32)

# ============ Artifacts ============
def _find(path_globs: List[str]) -> str | None:
    for patt in path_globs:
        m = glob.glob(patt)
        if m:
            return m[0]
    return None

def load_artifacts():
    model_path = _find([
        os.path.join(MODEL_DIR, 'ultrasonic_plant_cnn.keras'),
        os.path.join(MODEL_DIR, '*.keras'),
    ])
    scaler_path = _find([
        os.path.join(MODEL_DIR, 'scaler_params.npz'),
        os.path.join(MODEL_DIR, '*scaler*.npz'),
        os.path.join(MODEL_DIR, '*normalization*.npz'),
    ])
    label_path = _find([
        os.path.join(MODEL_DIR, 'label_encoder.pkl'),
        os.path.join(MODEL_DIR, '*label*encoder*.pkl'),
    ])
    if not model_path or not scaler_path or not label_path:
        raise SystemExit("[!] Missing model/scaler/labels in MODEL_DIR")
    model = tf.keras.models.load_model(model_path)
    d = np.load(scaler_path)
    mean = d['mean'] if 'mean' in d.files else d.get('scaler_mean')
    scale = d['scale'] if 'scale' in d.files else d.get('scaler_scale')
    with open(label_path, 'rb') as f:
        le = pickle.load(f)
    return model, mean, scale, le

# ============ DB (Postgres) ============
def db_connect():
    try:
        return psycopg2.connect(POSTGRES_DSN)
    except Exception as e:
        raise SystemExit(f"[DB] connection failed: {e}")

def db_insert_many(rows: List[Tuple[str, float]]) -> int:
    """
    rows = [(predicted_class, confidence), ...]
    prediction_time נקבע אוטומטית ע"י ה-DB (DEFAULT CURRENT_TIMESTAMP)
    """
    if not rows:
        return 0
    query = """
        INSERT INTO ultrasonic_plant_predictions (predicted_class, confidence)
        VALUES %s
    """
    with db_connect() as conn, conn.cursor() as cur:
        execute_values(cur, query, rows)
    return len(rows)

# ============ Predict ============
def predict_one(model, mean, scale, le, path: Path) -> Tuple[str, float]:
    audio, sr = load_audio(path)
    feats = extract_features(audio, sr)
    spec = create_melspec(audio, sr)
    feats_norm = (feats - mean) / scale
    fb = feats_norm[np.newaxis, :]
    sb = spec[np.newaxis, ..., np.newaxis]
    probs = model.predict([fb, sb], verbose=0)[0]
    idx = int(np.argmax(probs))
    conf = float(probs[idx])
    label = str(le.classes_[idx])
    return label, conf

# ============ Main ============
def main():
    print(f"INPUT_DIR={INPUT_DIR}\nMODEL_DIR={MODEL_DIR}\nPOSTGRES_DSN={POSTGRES_DSN}")
    model, mean, scale, le = load_artifacts()

    # אם PERIOD_DAYS <= 0 – לא מסננים לפי זמן בכלל
    use_time_filter = PERIOD_DAYS > 0
    if use_time_filter:
        cutoff = dt.datetime.utcnow() - dt.timedelta(days=PERIOD_DAYS)
        print(f"[i] Time filter enabled: last {PERIOD_DAYS} days (cutoff UTC={cutoff.isoformat()}Z)")
    else:
        print("[i] Time filter disabled (PERIOD_DAYS<=0): processing ALL .wav files")

    # איסוף wav בצורה case-insensitive
    wavs: List[Path] = []
    for p in Path(INPUT_DIR).rglob('*'):
        try:
            if p.is_file() and p.suffix.lower() == '.wav':
                if not use_time_filter:
                    wavs.append(p)
                else:
                    mtime = dt.datetime.utcfromtimestamp(p.stat().st_mtime)
                    if mtime >= cutoff:
                        wavs.append(p)
        except Exception:
            continue

    if not wavs:
        print("[i] No WAV files found.")
        return 0

    batch_pg: List[Tuple[str, float]] = []
    inserted_api = 0

    # חישוב יחסיות עבור object_key ל-db_api
    input_dir_abs = str(Path(INPUT_DIR).resolve())

    for p in sorted(wavs):
        try:
            label, conf = predict_one(model, mean, scale, le, p)
            if conf >= CONF_THRESHOLD:
                batch_pg.append((label, conf))
            print(f"OK {p} -> {label} ({conf:.3f})")

            # דיווח ל-db_api (לא חובה)
            if DB_API_REPORT and _HAS_DB_API_CLIENT:
                # קביעת object_key יחסית ל-INPUT_DIR אם אפשר
                p_abs = str(p.resolve())
                if p_abs.startswith(input_dir_abs):
                    try:
                        object_key = str(Path(p_abs).relative_to(input_dir_abs)).replace("\\", "/")
                    except Exception:
                        object_key = p.name
                else:
                    object_key = p.name

                meta = {
                    "bucket": DB_API_BUCKET,
                    "object_key": object_key,
                    "service": "plant_stress",
                    "mime": "audio/wav",
                    "timestamp": dt.datetime.utcnow().isoformat() + "Z",
                    "predicted_class": label,
                    "confidence": conf,
                    "tags": ["ultrasonic", "2ms@500kHz"],
                }
                ok = write_db_entry(meta)
                if ok:
                    inserted_api += 1

        except Exception as e:
            print(f"[!] Fail {p}: {e}")

    inserted_pg = db_insert_many(batch_pg)
    print(f"Done. processed={len(wavs)} inserted_pg={inserted_pg} inserted_api={inserted_api if DB_API_REPORT else 'disabled'}")
    return inserted_pg

if __name__ == '__main__':
    sys.exit(0 if main() is not None else 1)
