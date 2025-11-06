import os, sys, time, pickle, datetime as dt
from pathlib import Path
import re
import numpy as np
import librosa
import tensorflow as tf
import psycopg2, psycopg2.extras
import pytz
from io import BytesIO
import soundfile as sf
from minio import Minio

# ======== Environment ========
MODEL_DIR     = os.getenv("MODEL_DIR", "/models")
POSTGRES_DSN  = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/postgres")

# MinIO (כמו שביקשת)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS   = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET   = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_BUCKET   = os.getenv("MINIO_BUCKET", "sound")
MINIO_PREFIX   = os.getenv("MINIO_PREFIX", "plants/")
MINIO_SECURE   = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Date / TZ
TIMEZONE       = os.getenv("TIMEZONE", "Asia/Jerusalem")
PROCESS_DATE   = os.getenv("PROCESS_DATE", "").strip()  # אופציונלי: YYYY-MM-DD עבור עיבוד רטרו

# Confidence
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.60"))

# ======== Audio Params (2ms @ 500kHz) ========
SAMPLE_RATE = 500_000
DURATION_MS = 2
N_SAMPLES   = int(SAMPLE_RATE * DURATION_MS / 1000)  # 1000 samples
N_FFT       = 256
HOP_LENGTH  = 64
N_MELS      = 64

# ======== Watering Status Mapping ========
CLASS_TO_STATUS = {
    "Drought_Tomato":     "Watering required",
    "Drought_Tobacco":    "Watering required",
    "Control_Empty":      "Normal / Empty",
    "Control_Greenhouse": "Greenhouse noise / Normal",
}

# ======== Load model/scaler/encoder ========
model_path  = os.path.join(MODEL_DIR, "ultrasonic_plant_cnn.keras")
scaler_path = os.path.join(MODEL_DIR, "scaler_params.npz")
le_path     = os.path.join(MODEL_DIR, "label_encoder.pkl")

print(f"MODEL_DIR={MODEL_DIR}")
print(f"POSTGRES_DSN={POSTGRES_DSN}")
print(f"MINIO {MINIO_ENDPOINT=} {MINIO_BUCKET=} {MINIO_PREFIX=} {MINIO_SECURE=}")

# Try Keras 3 loader first (model was saved with keras 3)
try:
    import keras
    MODEL = keras.saving.load_model(model_path, compile=False)
except Exception as e_keras3:
    print(f"[!] Keras 3 load failed: {e_keras3} -- falling back to tf.keras")
    MODEL = tf.keras.models.load_model(model_path, compile=False)
sc = np.load(scaler_path)
SCALER_MEAN  = sc["mean"]
SCALER_SCALE = sc["scale"]
with open(le_path, "rb") as f:
    LABEL_ENCODER = pickle.load(f)

# ======== Helpers ========
FILENAME_RE = re.compile(
    r'(?P<sensor>[^/_]+)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<hour>\d{2})-(?P<minute>\d{2})\.wav$',
    re.IGNORECASE
)

def _tz():
    return pytz.timezone(TIMEZONE)

def _today_date():
    if PROCESS_DATE:
        return dt.datetime.strptime(PROCESS_DATE, "%Y-%m-%d").date()
    return dt.datetime.now(_tz()).date()

def parse_from_name(key: str):
    """
    מחלץ (sensor_id, recording_time_local) משם קובץ בסגנון mic1_2025-09-03_12-05.wav
    מחזיר (sensor_id:str, rec_time:aware-datetime-local) או (None, None) אם לא הסתדר.
    """
    m = FILENAME_RE.search(key)
    if not m:
        return None, None
    sensor = m.group("sensor")
    d = m.group("date")
    hh = int(m.group("hour"))
    mm = int(m.group("minute"))
    y, mon, dd = map(int, d.split("-"))
    local_dt = _tz().localize(dt.datetime(y, mon, dd, hh, mm, 0))
    return sensor, local_dt

def list_minio_wavs_for_date(client: Minio, bucket: str, prefix: str, the_date: dt.date):
    """
    מחזיר רשימת אובייקטים מ־MinIO עבור התאריך הנתון:
    1) מועדף: לפי תבנית בשם הקובץ (אם קיים תאריך בשם הקובץ והוא == the_date).
    2) אחרת (fallback): לפי last_modified שהומר ל־TIMEZONE והשוואת תאריך.
    """
    selected = []
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        key = obj.object_name
        if not key.lower().endswith(".wav"):
            continue
        sensor, rec_local = parse_from_name(key)
        if rec_local is not None:
            if rec_local.date() == the_date:
                selected.append((obj, sensor, rec_local))
            continue
        # fallback לפי last_modified
        lm_local = obj.last_modified.astimezone(_tz())
        if lm_local.date() == the_date:
            selected.append((obj, sensor, lm_local))  # sensor=None, time=lm_local
    return selected

def load_audio_from_minio(client: Minio, bucket: str, key: str):
    resp = client.get_object(bucket, key)
    try:
        data = resp.read()
    finally:
        resp.close(); resp.release_conn()
    bio = BytesIO(data)
    audio, sr = sf.read(bio, dtype="float32", always_2d=False)
    if isinstance(audio, np.ndarray) and audio.ndim == 2:
        audio = audio.mean(axis=1)
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
    feats = []
    feats.extend([np.mean(audio), np.std(audio), np.max(audio), np.min(audio),
                  np.var(audio), np.median(audio)])
    zcr = librosa.feature.zero_crossing_rate(audio, hop_length=HOP_LENGTH)[0]
    feats.extend([np.mean(zcr), np.std(zcr), np.max(zcr)])
    fft = np.abs(np.fft.fft(audio))[:len(audio)//2]
    feats.extend([np.mean(fft), np.std(fft), np.max(fft), np.argmax(fft)])
    try:
        sc = librosa.feature.spectral_centroid(y=audio, sr=sr, hop_length=HOP_LENGTH)[0]
        ro = librosa.feature.spectral_rolloff(y=audio, sr=sr, hop_length=HOP_LENGTH)[0]
        feats.extend([np.mean(sc), np.mean(ro)])
    except Exception:
        feats.extend([0.0, 0.0])
    rms = librosa.feature.rms(y=audio, hop_length=HOP_LENGTH)[0]
    feats.extend([np.mean(rms), np.std(rms)])
    return np.array(feats, dtype=np.float32)

def create_spectrogram_features(audio: np.ndarray, sr: int):
    mel = librosa.feature.melspectrogram(
        y=audio, sr=sr, n_fft=N_FFT, hop_length=HOP_LENGTH,
        n_mels=N_MELS, fmax=sr//2
    )
    mel_db  = librosa.power_to_db(mel, ref=np.max)
    mel_norm = (mel_db - mel_db.min()) / (mel_db.max() - mel_db.min() + 1e-8)
    return mel_norm.astype(np.float32)

def normalize_features(x: np.ndarray):
    return (x - SCALER_MEAN) / SCALER_SCALE

# ======== DB ========
def ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ultrasonic_plant_predictions (
          id               BIGSERIAL PRIMARY KEY,
          file             TEXT,
          sensor_id        TEXT,
          recording_time   TIMESTAMPTZ,
          predicted_class  TEXT,
          confidence       DOUBLE PRECISION,
          watering_status  TEXT,
          status           TEXT,
          prediction_time  TIMESTAMPTZ DEFAULT now()
        );
        """)
        # אינדקסים ומניעת כפילויות (בטוח להרצה חוזרת)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_upp_rec_time ON ultrasonic_plant_predictions(recording_time);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_upp_sensor ON ultrasonic_plant_predictions(sensor_id);")
        cur.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uniq_sensor_time_file'
          ) THEN
            ALTER TABLE ultrasonic_plant_predictions
            ADD CONSTRAINT uniq_sensor_time_file UNIQUE (sensor_id, recording_time, file);
          END IF;
        END$$;
        """)
    conn.commit()

def insert_rows(conn, rows):
    """
    rows: (file, sensor_id, recording_time, predicted_class, confidence, watering_status, status, prediction_time)
    """
    sql = """
    INSERT INTO ultrasonic_plant_predictions
      (file, sensor_id, recording_time, predicted_class, confidence, watering_status, status, prediction_time)
    VALUES %s
    ON CONFLICT ON CONSTRAINT uniq_sensor_time_file DO NOTHING
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, page_size=500)
    conn.commit()

# ======== Main ========
def main():
    the_date = _today_date()
    print(f"[i] Processing MinIO objects for date={the_date} (TZ={TIMEZONE})")

    client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS, secret_key=MINIO_SECRET, secure=MINIO_SECURE)
    objs = list_minio_wavs_for_date(client, MINIO_BUCKET, MINIO_PREFIX, the_date)
    if not objs:
        print("No WAV objects for that date. Exiting.")
        return 0

    try:
        conn = psycopg2.connect(POSTGRES_DSN)
        ensure_table(conn)
    except Exception as e:
        print(f"[!] Postgres connection error: {e}")
        return 2

    batch = []
    ok, fail = 0, 0
    t0 = time.time()

    for (obj, sensor, rec_local_dt) in objs:
        key = obj.object_name
        s3url = f"s3://{MINIO_BUCKET}/{key}"
        try:
            # אם sensor לא הוחלץ מהשם—ננסה לפחות להוציא prefix כחלופה
            if sensor is None:
                sensor, _ = parse_from_name(key)  # עוד ניסיון
            if sensor is None:
                # fallback: ננסה לקחת את החלק הראשון מהשם
                sensor = key.split("/")[-1].split("_")[0]

            audio, sr = load_audio_from_minio(client, MINIO_BUCKET, key)
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
                s3url,
                str(sensor),
                rec_local_dt.astimezone(pytz.UTC),  # נשמור UTC בבסיס הנתונים
                str(pred_class),
                conf,
                watering_status,
                "Success",
                dt.datetime.utcnow()
            ))
            ok += 1
            print(f"OK {s3url} [{sensor} @ {rec_local_dt.isoformat()}] -> {pred_class} ({conf:.3f})")
        except Exception as e:
            fail += 1
            batch.append((s3url, str(sensor) if sensor else None,
                          rec_local_dt.astimezone(pytz.UTC) if rec_local_dt else None,
                          "", None, "", f"Error: {e}", dt.datetime.utcnow()))
            print(f"[ERR] {s3url} -> {e}")

    try:
        if batch:
            insert_rows(conn, batch)
            print(f"Inserted {len(batch)} rows (dedup via UNIQUE).")
    except Exception as e:
        print(f"[!] Insert error: {e}")
        return 3
    finally:
        try: conn.close()
        except: pass

    dt_sec = time.time() - t0
    print(f"Done. processed={len(objs)} ok={ok} fail={fail} elapsed_sec={dt_sec:.1f}")
    return 0

if __name__ == "__main__":
    sys.exit(main())