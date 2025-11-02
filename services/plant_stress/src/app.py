import os, sys, time, glob, pickle, datetime as dt
from pathlib import Path
import numpy as np
import librosa
import tensorflow as tf
import psycopg2
import psycopg2.extras

# ======== Environment Config ========
INPUT_DIR    = os.environ.get("INPUT_DIR", "/data/inbox")
MODEL_DIR    = os.environ.get("MODEL_DIR", "/models")
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/postgres")
PERIOD_DAYS  = int(os.environ.get("PERIOD_DAYS", "0"))   # 0 = process all files

# ======== Audio Parameters (2ms @ 500kHz) ========
SAMPLE_RATE = 500_000
DURATION_MS = 2
N_SAMPLES   = int(SAMPLE_RATE * DURATION_MS / 1000)  # 1000 samples
N_FFT       = 256
HOP_LENGTH  = 64
N_MELS      = 64

# ======== Watering Status Mapping ========
CLASS_TO_STATUS = {
    "Drought_Tomato":   "Watering required",
    "Drought_Tobacco":  "Watering required",
    "Control_Empty":    "Normal / Empty",
    "Control_Greenhouse": "Greenhouse noise / Normal",
}
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.60"))

# ======== Load Model / Scaler / LabelEncoder ========
model_path = os.path.join(MODEL_DIR, "ultrasonic_plant_cnn.keras")
scaler_path = os.path.join(MODEL_DIR, "scaler_params.npz")
le_path     = os.path.join(MODEL_DIR, "label_encoder.pkl")

print(f"INPUT_DIR={INPUT_DIR}")
print(f"MODEL_DIR={MODEL_DIR}")
print(f"POSTGRES_DSN={POSTGRES_DSN}")

MODEL = tf.keras.models.load_model(model_path)

sc = np.load(scaler_path)
SCALER_MEAN  = sc["mean"]
SCALER_SCALE = sc["scale"]

with open(le_path, "rb") as f:
    LABEL_ENCODER = pickle.load(f)

# ======== Helper Functions ========
def load_and_preprocess_audio(file_path: str):
    """Load audio, resample to 500kHz, crop/pad to 2ms (1000 samples)."""
    audio, sr = librosa.load(file_path, sr=None, mono=True)
    if sr != SAMPLE_RATE:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)
        sr = SAMPLE_RATE

    if len(audio) > N_SAMPLES:
        start = (len(audio) - N_SAMPLES) // 2
        audio = audio[start:start + N_SAMPLES]
    elif len(audio) < N_SAMPLES:
        pad = N_SAMPLES - len(audio)
        audio = np.pad(audio, (0, pad), mode='constant')

    return audio.astype(np.float32), sr

def extract_ultrasonic_features(audio: np.ndarray, sr: int):
    """Short time/frequency features for 2ms window."""
    feats = []
    feats.extend([np.mean(audio), np.std(audio), np.max(audio), np.min(audio),
                  np.var(audio), np.median(audio)])
    zcr = librosa.feature.zero_crossing_rate(audio, hop_length=HOP_LENGTH)[0]
    feats.extend([np.mean(zcr), np.std(zcr), np.max(zcr)])
    fft = np.abs(np.fft.fft(audio))[:len(audio)//2]
    feats.extend([np.mean(fft), np.std(fft), np.max(fft), np.argmax(fft)])
    try:
        spectral_centroids = librosa.feature.spectral_centroid(y=audio, sr=sr, hop_length=HOP_LENGTH)[0]
        spectral_rolloff   = librosa.feature.spectral_rolloff(y=audio, sr=sr, hop_length=HOP_LENGTH)[0]
        feats.extend([np.mean(spectral_centroids), np.mean(spectral_rolloff)])
    except Exception:
        feats.extend([0.0, 0.0])
    rms = librosa.feature.rms(y=audio, hop_length=HOP_LENGTH)[0]
    feats.extend([np.mean(rms), np.std(rms)])
    return np.array(feats, dtype=np.float32)

def create_spectrogram_features(audio: np.ndarray, sr: int):
    """Small Mel-spectrogram adapted for 2ms."""
    mel = librosa.feature.melspectrogram(
        y=audio, sr=sr, n_fft=N_FFT, hop_length=HOP_LENGTH,
        n_mels=N_MELS, fmax=sr//2
    )
    mel_db  = librosa.power_to_db(mel, ref=np.max)
    mel_norm = (mel_db - mel_db.min()) / (mel_db.max() - mel_db.min() + 1e-8)
    return mel_norm.astype(np.float32)

def normalize_features(x: np.ndarray):
    return (x - SCALER_MEAN) / SCALER_SCALE

def files_to_process(root: str, period_days: int):
    p = Path(root)
    if not p.exists():
        print(f"[!] INPUT_DIR not found: {root}")
        return []
    exts = {".wav", ".WAV"}
    allf = [str(pp) for pp in p.rglob("*") if pp.suffix in exts]
    if period_days <= 0:
        print("[i] Time filter disabled (PERIOD_DAYS<=0): processing ALL .wav files")
        return sorted(allf)
    cutoff = time.time() - period_days * 86400
    return sorted([f for f in allf if Path(f).stat().st_mtime >= cutoff])

def ensure_table(conn):
    sql = """
    CREATE TABLE IF NOT EXISTS ultrasonic_plant_predictions (
      id               BIGSERIAL PRIMARY KEY,
      file             TEXT,
      predicted_class  TEXT,
      confidence       DOUBLE PRECISION,
      watering_status  TEXT,
      status           TEXT,
      prediction_time  TIMESTAMPTZ DEFAULT now()
    );
    """
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

def insert_rows(conn, rows):
    """rows: list of tuples(file, predicted_class, confidence, watering_status, status, prediction_time)"""
    sql = """
    INSERT INTO ultrasonic_plant_predictions
      (file, predicted_class, confidence, watering_status, status, prediction_time)
    VALUES %s
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, page_size=500)
    conn.commit()

# ======== Main Run ========
def main():
    files = files_to_process(INPUT_DIR, PERIOD_DAYS)
    if not files:
        print("No files to process. Exiting.")
        return 0

    try:
        conn = psycopg2.connect(POSTGRES_DSN)
        ensure_table(conn)
    except Exception as e:
        print(f"[!] Postgres connection error: {e}")
        return 2

    batch = []
    ok, fail = 0, 0
    start = time.time()

    for fpath in files:
        try:
            audio, sr = load_and_preprocess_audio(fpath)
            feats = extract_ultrasonic_features(audio, sr)
            spec  = create_spectrogram_features(audio, sr)

            feats_norm = normalize_features(feats)
            feats_batch = feats_norm[np.newaxis, :]
            spec_batch  = spec[np.newaxis, ..., np.newaxis]

            probs = MODEL.predict([feats_batch, spec_batch], verbose=0)[0]
            idx   = int(np.argmax(probs))
            pred_class = LABEL_ENCODER.classes_[idx]
            conf  = float(probs[idx])

            watering_status = CLASS_TO_STATUS.get(pred_class, "Undefined")
            if conf < CONFIDENCE_THRESHOLD:
                watering_status = f"{watering_status} (Uncertain)"

            batch.append((
                fpath, str(pred_class), conf, watering_status, "Success",
                dt.datetime.utcnow()
            ))
            ok += 1
            print(f"OK {fpath} -> {pred_class} ({conf:.3f})")
        except Exception as e:
            fail += 1
            batch.append((fpath, "", None, "", f"Error: {e}", dt.datetime.utcnow()))
            print(f"[ERR] {fpath} -> {e}")


    # Write to Postgres
    try:
        if batch:
            insert_rows(conn, batch)
            print(f"Inserted {len(batch)} rows to Postgres.")
    except Exception as e:
        print(f"[!] Insert error: {e}")
        return 3
    finally:
        try:
            conn.close()
        except Exception:
            pass

    elapsed = time.time() - start
    print(f"Done. processed={len(files)} ok={ok} fail={fail} elapsed_sec={elapsed:.1f}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
