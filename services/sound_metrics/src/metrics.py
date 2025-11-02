# local_metrics_minio.py
import os, re, time, math
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, soundfile as sf
from prometheus_client import Gauge, start_http_server
from minio import Minio
from io import BytesIO

try:
    from pydub import AudioSegment
    HAVE_PYDUB = True
except Exception:
    HAVE_PYDUB = False

# === Environment ===
ADDR           = os.getenv("ADDR", "0.0.0.0")
PORT           = int(os.getenv("PORT", "8001"))
WINDOW_MIN     = int(os.getenv("WINDOW_MIN", 5))
FRAME_SEC      = float(os.getenv("FRAME_SEC", 0.1))
THRESHOLD      = float(os.getenv("THRESHOLD", 0.01))
USE_UTC        = os.getenv("USE_UTC", "false").lower() == "true"
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS   = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET   = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_BUCKET   = os.getenv("MINIO_BUCKET", "telemetry")
MINIO_PREFIX   = os.getenv("MINIO_PREFIX", "sounds/")

ALLOWED_EXTS = {".wav", ".flac", ".ogg", ".aiff", ".aif", ".au", ".mp3", ".m4a", ".aac", ".opus"}
FFMPEG_EXTS   = {".mp3", ".m4a", ".aac"}

def now_time():
    return datetime.utcnow() if USE_UTC else datetime.now()

# === Prometheus metrics ===
g_avg_rms = Gauge("sound_avg_volume", "5m avg RMS", ["mic_id"])
g_std_rms = Gauge("sound_std_volume", "5m std of RMS", ["mic_id"])
g_uptime  = Gauge("sound_mic_uptime_ratio", "5m uptime ratio", ["mic_id"])

# === Filename pattern: <mic>_YYYY-MM-DD_HH-MM.ext ===
FNAME_RE = re.compile(
    r"^(?P<mic>[^_]+)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<h>\d{2})-(?P<m>\d{2})$",
    re.IGNORECASE
)

def parse_name(fname: str):
    p = Path(fname)
    m = FNAME_RE.match(p.stem)
    if not m:
        return None, None
    mic = m.group("mic")
    ts = datetime.strptime(f"{m.group('date')}_{m.group('h')}-{m.group('m')}", "%Y-%m-%d_%H-%M")
    return mic, ts

def window_start_for(ts: datetime) -> datetime:
    bucket_min = (ts.minute // WINDOW_MIN) * WINDOW_MIN
    return ts.replace(minute=bucket_min, second=0, microsecond=0)

# === Audio processing ===
def load_audio_bytes(data: bytes, ext: str):
    if ext in FFMPEG_EXTS:
        if not HAVE_PYDUB:
            raise RuntimeError("pydub (with FFmpeg) required for compressed audio")
        audio = AudioSegment.from_file(BytesIO(data))
        arr = np.array(audio.get_array_of_samples())
        if audio.channels > 1:
            arr = arr.reshape((-1, audio.channels)).mean(axis=1)
        max_int = float(1 << (8 * audio.sample_width - 1))
        samples = arr.astype(np.float32) / max_int
        return samples, audio.frame_rate
    else:
        with sf.SoundFile(BytesIO(data)) as f:
            samples = f.read(always_2d=False)
            sr = f.samplerate
        if samples.ndim == 2:
            samples = samples.mean(axis=1)
        return samples, sr

def process_audio_bytes(data: bytes, ext: str):
    samples, sr = load_audio_bytes(data, ext)
    if not samples.size:
        return 0.0, 0.0, 0, 0
    rms_all = float(np.sqrt(np.mean(samples**2)))
    std_all = float(np.std(samples))
    frame = max(1, int(sr * FRAME_SEC))
    active = total = 0
    for i in range(0, len(samples), frame):
        seg = samples[i:i+frame]
        if len(seg) == 0:
            continue
        r = float(np.sqrt(np.mean(seg**2)))
        if r >= THRESHOLD:
            active += 1
        total += 1
    return rms_all, std_all, active, total

def flush_finished_windows(now: datetime, agg):
    finished = []
    for (mic, wstart), s in list(agg.items()):
        if (wstart + timedelta(minutes=WINDOW_MIN)) <= now:
            n = s["n"]
            if n:
                mean = s["sum"] / n
                var = (s["sum_sq"] / n) - mean**2
                std = math.sqrt(max(var, 0))
                uptime = s["active_frames"] / s["total_frames"] if s["total_frames"] else 0.0
                g_avg_rms.labels(mic).set(mean)
                g_std_rms.labels(mic).set(std)
                g_uptime.labels(mic).set(uptime)
                print(f"[FLUSH] mic={mic} window={wstart:%Y-%m-%d %H:%M} RMS={mean:.5f} STD={std:.5f} uptime={uptime:.3f}")
            finished.append((mic, wstart))
    for key in finished:
        del agg[key]

def apply_delta(slot, delta, sign):
    """Apply (sign=+1 add, sign=-1 subtract) a contribution delta to an agg slot."""
    slot["sum"]           += sign * delta["sum"]
    slot["sum_sq"]        += sign * delta["sum_sq"]
    slot["n"]             += sign * delta["n"]
    slot["active_frames"] += sign * delta["active_frames"]
    slot["total_frames"]  += sign * delta["total_frames"]

def main():
    start_http_server(PORT, addr=ADDR)
    print(f"✅ MinIO Metrics available at: http://{ADDR}:{PORT}/metrics")

    # MinIO client
    client = Minio(MINIO_ENDPOINT, MINIO_ACCESS, MINIO_SECRET, secure=False)

    # seen: fname -> etag (to detect updates/overwrites)
    seen = {}
    # agg: (mic, wstart) -> accumulators
    agg = {}
    # contrib: fname -> {"wstart": datetime, "delta": {...}}
    # keeps last contribution of each file, so we can subtract it before re-adding
    contrib = {}

    while True:
        now = now_time()
        try:
            objects = client.list_objects(MINIO_BUCKET, prefix=MINIO_PREFIX, recursive=True)
        except Exception as e:
            print(f"[WARN] Failed to list objects from MinIO: {e}")
            time.sleep(10)
            continue

        for obj in objects:
            fname_full = obj.object_name  # includes prefix/path
            fname = Path(fname_full).name
            ext = Path(fname).suffix.lower()
            if ext not in ALLOWED_EXTS:
                continue

            etag = getattr(obj, "etag", None)

            # If we already processed this exact version (same etag), skip
            if fname in seen and seen[fname] == etag:
                continue

            mic, ts = parse_name(fname)
            if not mic:
                # skip files that don't match naming scheme
                continue

            try:
                resp = client.get_object(MINIO_BUCKET, fname_full)
                data = resp.read()
            except Exception as e:
                print(f"[ERROR] get_object {fname}: {e}")
                # ensure the connection is closed even on error
                try:
                    resp.close(); resp.release_conn()
                except Exception:
                    pass
                continue
            finally:
                try:
                    resp.close(); resp.release_conn()
                except Exception:
                    pass

            try:
                rms, _std, active, total = process_audio_bytes(data, ext)
            except Exception as e:
                print(f"[ERROR] process_audio {fname}: {e}")
                continue

            # Prepare new contribution for this file
            new_wstart = window_start_for(ts)
            new_delta = {
                "sum": float(rms),
                "sum_sq": float(rms * rms),
                "n": 1,
                "active_frames": int(active),
                "total_frames": int(total),
            }

            # If this file contributed before, remove its previous contribution first
            if fname in contrib:
                prev = contrib[fname]
                prev_wstart = prev["wstart"]
                prev_delta  = prev["delta"]
                prev_key = (mic, prev_wstart)
                # Only subtract if the previous window slot still exists
                if prev_key in agg:
                    apply_delta(agg[prev_key], prev_delta, sign=-1)

            # Now add the new contribution to the appropriate window slot
            key = (mic, new_wstart)
            slot = agg.setdefault(key, {"sum": 0.0, "sum_sq": 0.0, "n": 0, "active_frames": 0, "total_frames": 0})
            apply_delta(slot, new_delta, sign=+1)

            # Remember the last seen etag and contribution
            seen[fname] = etag
            contrib[fname] = {"wstart": new_wstart, "delta": new_delta}

            print(f"[OK] {fname} → mic={mic} RMS={rms:.4f} active={active}/{total} window={new_wstart:%Y-%m-%d %H:%M}")

        flush_finished_windows(now, agg)
        time.sleep(15)  # reduce load on MinIO

if __name__ == "__main__":
    main()
