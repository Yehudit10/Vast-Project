import os, sys, time, pickle, datetime as dt
from pathlib import Path
import re
import uuid
import json
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

# MinIO
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS   = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET   = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_BUCKET   = os.getenv("MINIO_BUCKET", "sound")
MINIO_PREFIX   = os.getenv("MINIO_PREFIX", "plants/")
MINIO_SECURE   = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Defaults for required GUI fields
DEFAULT_AREA = os.getenv("DEFAULT_AREA", "unknown").strip()
DEFAULT_LAT  = os.getenv("DEFAULT_LAT", "0.0").strip()
DEFAULT_LON  = os.getenv("DEFAULT_LON", "0.0").strip()
DEFAULT_IMAGE_URL = os.getenv("DEFAULT_IMAGE_URL", "https://example.com/placeholder.jpg").strip()
DEFAULT_VOD       = os.getenv("DEFAULT_VOD", "https://example.com/placeholder.mp4").strip()
DEFAULT_HLS       = os.getenv("DEFAULT_HLS", "https://example.com/placeholder.m3u8").strip()

# Date / TZ
TIMEZONE       = os.getenv("TIMEZONE", "Asia/Jerusalem")
PROCESS_DATE   = os.getenv("PROCESS_DATE", "").strip()  # YYYY-MM-DD (optional backfill)

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

# ======== Alerts / Kafka ========
ENABLE_ALERTS = os.getenv("ENABLE_ALERTS", "true").lower() == "true"
ALERT_TOPIC   = os.getenv("ALERT_TOPIC", "alerts")
ALERT_TYPE    = os.getenv("ALERT_TYPE", "plant_drought_detected")
ALERT_AREA    = os.getenv("ALERT_AREA", "").strip()
ALERT_LAT     = os.getenv("ALERT_LAT", "").strip()
ALERT_LON     = os.getenv("ALERT_LON", "").strip()
ALERT_IMAGE_URL = os.getenv("ALERT_IMAGE_URL", "").strip()
ALERT_VOD       = os.getenv("ALERT_VOD", "").strip()
ALERT_HLS       = os.getenv("ALERT_HLS", "").strip()

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
KAFKA_CLIENT_ID = os.getenv("KAFKA_CLIENT_ID", "plant-stress-producer")
KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "").strip()
KAFKA_SASL_MECHANISM    = os.getenv("KAFKA_SASL_MECHANISM", "").strip()
KAFKA_SASL_USERNAME     = os.getenv("KAFKA_SASL_USERNAME", "").strip()
KAFKA_SASL_PASSWORD     = os.getenv("KAFKA_SASL_PASSWORD", "").strip()
KAFKA_SSL_CA            = os.getenv("KAFKA_SSL_CA", "").strip()
KAFKA_SSL_CERT          = os.getenv("KAFKA_SSL_CERT", "").strip()
KAFKA_SSL_KEY           = os.getenv("KAFKA_SSL_KEY", "").strip()

# ======== Load model/scaler/encoder ========
model_path  = os.path.join(MODEL_DIR, "ultrasonic_plant_cnn.keras")
scaler_path = os.path.join(MODEL_DIR, "scaler_params.npz")
le_path     = os.path.join(MODEL_DIR, "label_encoder.pkl")

print(f"MODEL_DIR={MODEL_DIR}")
print(f"POSTGRES_DSN={POSTGRES_DSN}")
print(f"MINIO {MINIO_ENDPOINT=} {MINIO_BUCKET=} {MINIO_PREFIX=} {MINIO_SECURE=}")
print(f"ALERTS enable={ENABLE_ALERTS} topic={ALERT_TOPIC} bootstrap={KAFKA_BOOTSTRAP}")

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

# ======== Kafka Producer (lazy, dual-impl) ========
class _KafkaProducer:
    def __init__(self):
        self.impl = None
        self.mode = None
        self._init_producer()

    def _init_producer(self):
        if not ENABLE_ALERTS:
            return
        try:
            from confluent_kafka import Producer
            conf = {"bootstrap.servers": KAFKA_BOOTSTRAP, "client.id": KAFKA_CLIENT_ID}
            if KAFKA_SECURITY_PROTOCOL: conf["security.protocol"] = KAFKA_SECURITY_PROTOCOL
            if KAFKA_SASL_MECHANISM:    conf["sasl.mechanisms"]   = KAFKA_SASL_MECHANISM
            if KAFKA_SASL_USERNAME:     conf["sasl.username"]     = KAFKA_SASL_USERNAME
            if KAFKA_SASL_PASSWORD:     conf["sasl.password"]     = KAFKA_SASL_PASSWORD
            if KAFKA_SSL_CA:   conf["ssl.ca.location"]        = KAFKA_SSL_CA
            if KAFKA_SSL_CERT: conf["ssl.certificate.location"]= KAFKA_SSL_CERT
            if KAFKA_SSL_KEY:  conf["ssl.key.location"]       = KAFKA_SSL_KEY
            self.impl = Producer(conf)
            self.mode = "confluent"
            print("[Kafka] Using confluent-kafka Producer")
            return
        except Exception as e:
            print(f"[Kafka] confluent-kafka unavailable: {e}")

        try:
            from kafka import KafkaProducer
            kwargs = {
                "bootstrap_servers": KAFKA_BOOTSTRAP,
                "client_id": KAFKA_CLIENT_ID,
                "value_serializer": lambda v: json.dumps(v).encode("utf-8"),
                "linger_ms": 10,
                "acks": "all",
            }
            if KAFKA_SECURITY_PROTOCOL: kwargs["security_protocol"] = KAFKA_SECURITY_PROTOCOL
            if KAFKA_SASL_MECHANISM:    kwargs["sasl_mechanism"]    = KAFKA_SASL_MECHANISM
            if KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD:
                kwargs["sasl_plain_username"] = KAFKA_SASL_USERNAME
                kwargs["sasl_plain_password"] = KAFKA_SASL_PASSWORD
            if KAFKA_SSL_CA:   kwargs["ssl_cafile"] = KAFKA_SSL_CA
            if KAFKA_SSL_CERT: kwargs["ssl_certfile"] = KAFKA_SSL_CERT
            if KAFKA_SSL_KEY:  kwargs["ssl_keyfile"] = KAFKA_SSL_KEY
            self.impl = KafkaProducer(**kwargs)
            self.mode = "kafka-python"
            print("[Kafka] Using kafka-python Producer")
        except Exception as e2:
            print(f"[Kafka] kafka-python unavailable: {e2}")
            self.impl = None
            self.mode = None

    def send(self, topic: str, value: dict):
        if not ENABLE_ALERTS or self.impl is None:
            return False
        if self.mode == "confluent":
            try:
                self.impl.produce(topic, value=json.dumps(value).encode("utf-8"))
                self.impl.poll(0)
                return True
            except Exception as e:
                print(f"[Kafka] produce error (confluent): {e}")
                return False
        elif self.mode == "kafka-python":
            try:
                fut = self.impl.send(topic, value=value)
                fut.get(timeout=5)
                return True
            except Exception as e:
                print(f"[Kafka] produce error (kafka-python): {e}")
                return False
        return False

    def flush(self):
        try:
            if self.mode == "confluent" and self.impl is not None:
                self.impl.flush(5)
            elif self.mode == "kafka-python" and self.impl is not None:
                self.impl.flush()
        except Exception:
            pass

KAFKA_PRODUCER = _KafkaProducer()

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
    mic1_2025-09-03_12-05.wav -> (sensor_id, aware-local-datetime) or (None, None)
    """
    m = FILENAME_RE.search(key)
    if not m:
        return None, None
    sensor = m.group("sensor")
    y, mon, dd = map(int, m.group("date").split("-"))
    hh = int(m.group("hour")); mm = int(m.group("minute"))
    local_dt = _tz().localize(dt.datetime(y, mon, dd, hh, mm, 0))
    return sensor, local_dt

def list_minio_wavs_for_date(client: Minio, bucket: str, prefix: str, the_date: dt.date):
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
        lm_local = obj.last_modified.astimezone(_tz())
        if lm_local.date() == the_date:
            selected.append((obj, sensor, lm_local))
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
def ensure_predictions_table(conn):
    """Match your schema exactly: no sensor_id, no recording_time."""
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ultrasonic_plant_predictions (
          id               BIGSERIAL PRIMARY KEY,
          file             TEXT,
          predicted_class  TEXT,
          confidence       DOUBLE PRECISION,
          watering_status  TEXT,
          status           TEXT,
          prediction_time  TIMESTAMPTZ DEFAULT now()
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_upp_pred_time ON ultrasonic_plant_predictions(prediction_time DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_upp_class ON ultrasonic_plant_predictions(predicted_class);")
    conn.commit()

def ensure_alerts_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id    TEXT PRIMARY KEY,
            alert_type  TEXT,
            device_id   TEXT,
            started_at  TIMESTAMPTZ,
            ended_at    TIMESTAMPTZ,
            confidence  DOUBLE PRECISION,
            area        TEXT,
            lat         DOUBLE PRECISION,
            lon         DOUBLE PRECISION,
            severity    INT DEFAULT 1,
            image_url   TEXT,
            vod         TEXT,
            hls         TEXT,
            ack         BOOLEAN DEFAULT FALSE,
            meta        JSONB,
            created_at  TIMESTAMPTZ DEFAULT now(),
            updated_at  TIMESTAMPTZ DEFAULT now()
        );
        """)
        cur.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'set_updated_at') THEN
            CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $f$
            BEGIN
              NEW.updated_at = now();
              RETURN NEW;
            END;
            $f$ LANGUAGE plpgsql;
          END IF;
        END$$;
        """)
        cur.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_alerts_updated_at') THEN
            CREATE TRIGGER trg_alerts_updated_at
            BEFORE UPDATE ON alerts
            FOR EACH ROW
            EXECUTE PROCEDURE set_updated_at();
          END IF;
        END$$;
        """)
    conn.commit()

def insert_prediction_rows(conn, rows):
    """
    rows: iterable of tuples shaped exactly as the table:
      (file, predicted_class, confidence, watering_status, status, prediction_time)
    """
    sql = """
    INSERT INTO ultrasonic_plant_predictions
      (file, predicted_class, confidence, watering_status, status, prediction_time)
    VALUES %s
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, page_size=500)
    conn.commit()

def insert_alert_row(conn, alert: dict, started_at_dt: dt.datetime, ended_at_dt: dt.datetime | None = None, ack: bool = False):
    from psycopg2.extras import Json
    sql = """
    INSERT INTO alerts (
        alert_id, alert_type, device_id, started_at, ended_at,
        confidence, area, lat, lon, severity,
        image_url, vod, hls, ack, meta
    )
    VALUES (
        %(alert_id)s, %(alert_type)s, %(device_id)s, %(started_at)s, %(ended_at)s,
        %(confidence)s, %(area)s, %(lat)s, %(lon)s, %(severity)s,
        %(image_url)s, %(vod)s, %(hls)s, %(ack)s, %(meta)s
    )
    ON CONFLICT (alert_id) DO UPDATE
      SET updated_at = now()
    """
    params = {
        "alert_id":   alert["alert_id"],
        "alert_type": alert.get("alert_type"),
        "device_id":  alert.get("device_id"),
        "started_at": started_at_dt,
        "ended_at":   ended_at_dt,
        "confidence": alert.get("confidence"),
        "area":       alert.get("area"),
        "lat":        alert.get("lat"),
        "lon":        alert.get("lon"),
        "severity":   alert.get("severity"),
        "image_url":  alert.get("image_url"),
        "vod":        alert.get("vod"),
        "hls":        alert.get("hls"),
        "ack":        ack,
        "meta":       Json(alert.get("meta", {})),
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
    conn.commit()

# ======== Alert helpers ========
def _severity_from_confidence(conf: float) -> int:
    if conf >= 0.95: return 5
    if conf >= 0.90: return 4
    if conf >= 0.80: return 3
    if conf >= 0.70: return 2
    return 1

def _iso_utc(dt_aware) -> str:
    return dt_aware.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

def build_alert_payload(
    alert_type: str,
    device_id: str,
    started_at_utc: dt.datetime,
    confidence: float,
    s3url: str,
    area: str = "",
    lat: str = "",
    lon: str = "",
    image_url: str = "",
    vod: str = "",
    hls: str = "",
    extra_meta: dict | None = None,
) -> dict:
    def _to_float_or_default(v, default_s: str):
        try:
            if v is None or (isinstance(v, str) and v.strip() == ""):
                return float(default_s)
            return float(v)
        except Exception:
            return float(default_s)

    def _non_empty(value: str, default_value: str) -> str:
        v = (value or "").strip()
        return v if v else default_value

    area_f = _non_empty(area, DEFAULT_AREA)
    lat_f  = _to_float_or_default(lat, DEFAULT_LAT)
    lon_f  = _to_float_or_default(lon, DEFAULT_LON)
    image_f = _non_empty(image_url, DEFAULT_IMAGE_URL)
    vod_f   = _non_empty(vod, DEFAULT_VOD)
    hls_f   = _non_empty(hls, DEFAULT_HLS)

    payload = {
        "alert_id": str(uuid.uuid4()),
        "alert_type": alert_type,
        "device_id": device_id,
        "started_at": _iso_utc(started_at_utc),
        "confidence": round(confidence, 6),
        "severity": _severity_from_confidence(confidence),
        "area": area_f,
        "lat": lat_f,
        "lon": lon_f,
        "image_url": image_f,
        "vod": vod_f,
        "hls": hls_f,
        "meta": {
            "source": "ultrasonic_plant_classifier",
            "file": s3url,
        },
    }
    if extra_meta:
        payload["meta"].update(extra_meta)
    return payload

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
        ensure_alerts_table(conn)
        ensure_predictions_table(conn)
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
            if sensor is None:
                sensor, _ = parse_from_name(key)
            if sensor is None:
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

            # Save prediction row (schema: no sensor_id/recording_time)
            batch.append((
                s3url,              # file
                str(pred_class),    # predicted_class
                conf,               # confidence
                watering_status,    # watering_status
                "Success",          # status
                dt.datetime.utcnow()
            ))
            ok += 1
            print(f"OK {s3url} [{sensor} @ {rec_local_dt.isoformat()}] -> {pred_class} ({conf:.3f})")

            # Alerts for drought classes
            if ENABLE_ALERTS and pred_class in ("Drought_Tomato", "Drought_Tobacco"):
                rec_utc = rec_local_dt.astimezone(pytz.UTC) if rec_local_dt.tzinfo else pytz.UTC.localize(rec_local_dt)
                alert = build_alert_payload(
                    alert_type=ALERT_TYPE,
                    device_id=str(sensor),
                    started_at_utc=rec_utc,
                    confidence=conf,
                    s3url=s3url,
                    area=ALERT_AREA,
                    lat=ALERT_LAT,
                    lon=ALERT_LON,
                    image_url=ALERT_IMAGE_URL,
                    vod=ALERT_VOD,
                    hls=ALERT_HLS,
                    extra_meta={
                        "predicted_class": pred_class,
                        "watering_status": watering_status,
                        "model_dir": MODEL_DIR,
                        "sample_rate": SAMPLE_RATE,
                        "n_fft": N_FFT,
                        "n_mels": N_MELS
                    }
                )
                try:
                    insert_alert_row(conn, alert, started_at_dt=rec_utc, ended_at_dt=None, ack=False)
                    print(f"[Alert][DB] upsert alert_id={alert['alert_id']} device={alert['device_id']} severity={alert['severity']}")
                except Exception as e:
                    print(f"[Alert][DB] insert failed: {e}")

                # Send to Kafka (best effort)
                try:
                    ok_send = KAFKA_PRODUCER.send(ALERT_TOPIC, alert)
                    if ok_send:
                        print(f"[Alert] sent to topic={ALERT_TOPIC}: {alert['alert_id']}")
                    else:
                        print(f"[Alert] FAILED to send alert to topic={ALERT_TOPIC}")
                except Exception as e:
                    print(f"[Alert] send exception: {e}")

        except Exception as e:
            fail += 1
            print(f"[ERR] {s3url} -> {e}")
            batch.append((
                s3url,          # file
                "",             # predicted_class
                None,           # confidence
                "",             # watering_status
                f"Error: {e}",  # status
                dt.datetime.utcnow()
            ))

    try:
        if batch:
            insert_prediction_rows(conn, batch)
            print(f"Inserted {len(batch)} rows.")
    except Exception as e:
        print(f"[!] Insert error: {e}")
        return 3
    finally:
        try:
            conn.close()
        except:
            pass

    # Flush Kafka
    try:
        KAFKA_PRODUCER.flush()
    except Exception:
        pass

    dt_sec = time.time() - t0
    print(f"Done. processed={len(objs)} ok={ok} fail={fail} elapsed_sec={dt_sec:.1f}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
