# services/sound_metrics/src/metrics.py
import os, re, time, math
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, soundfile as sf
from prometheus_client import Gauge, Counter, start_http_server
from minio import Minio
from io import BytesIO

try:
    from pydub import AudioSegment
    HAVE_PYDUB = True
except Exception:
    HAVE_PYDUB = False

# === Environment ===
ADDR           = os.getenv("ADDR", "0.0.0.0")
PORT           = int(os.getenv("PORT", "8005"))
WINDOW_MIN     = int(os.getenv("WINDOW_MIN", 5))
FRAME_SEC      = float(os.getenv("FRAME_SEC", 0.1))
THRESHOLD      = float(os.getenv("THRESHOLD", 0.01))
USE_UTC        = os.getenv("USE_UTC", "false").lower() == "true"
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS   = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET   = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_BUCKET   = os.getenv("MINIO_BUCKET", "sound")
MINIO_PREFIX   = os.getenv("MINIO_PREFIX", "sounds/")
MINIO_PREFIXES = [p.strip() for p in os.getenv("MINIO_PREFIXES", "").split(",") if p.strip()]
if not MINIO_PREFIXES:
    MINIO_PREFIXES = [MINIO_PREFIX]

ALLOWED_EXTS = {".wav", ".flac", ".ogg", ".aiff", ".aif", ".au", ".mp3", ".m4a", ".aac", ".opus"}
FFMPEG_EXTS   = {".mp3", ".m4a", ".aac"}

def now_time():
    return datetime.utcnow() if USE_UTC else datetime.now()

# === Prometheus metrics (REAL metrics only) ===
g_avg_rms = Gauge("sound_avg_volume", "5m avg RMS", ["mic_id"])
g_std_rms = Gauge("sound_std_volume", "5m std of RMS", ["mic_id"])
g_uptime  = Gauge("sound_mic_uptime_ratio", "5m uptime ratio", ["mic_id"])
g_volume_db = Gauge("sound_volume_db", "5m average volume (as dB from RMS)", ["mic_id"])
g_mic_uptime_seconds = Gauge("mic_uptime_seconds", "Uptime seconds (in current window)", ["mic_id"])

# Debug / visibility counters
files_scanned_total = Counter("agcloud_files_scanned_total", "Total objects seen in MinIO", ["prefix"])
files_parsed_total  = Counter("agcloud_files_parsed_total", "Total audio files parsed", ["prefix", "mic_id"])
files_skipped_total = Counter("agcloud_files_skipped_total", "Skipped objects", ["prefix", "reason"])

# Filename pattern: <mic>_<YYYYMMDDThhmmssZ>.ext  e.g., MIC-01_20251109T232907Z.wav
# FNAME_RE = re.compile(r"^(?P<mic>[^_]+)_(?P<ts>\d{8}T\d{6}Z)$", re.IGNORECASE)

# Filename patterns (flexible):
# 1) <mic>_<YYYYMMDDThhmmssZ>
# 2) <mic>-<YYYYMMDDThhmmssZ>
# 3) <mic>_<YYYYMMDDThhmmss>    (no Z)
PATTERNS = [
    re.compile(r"^(?P<mic>[^_]+)_(?P<ts>\d{8}T\d{6}Z)$", re.IGNORECASE),
    re.compile(r"^(?P<mic>[^-]+)-(?P<ts>\d{8}T\d{6}Z)$", re.IGNORECASE),
    re.compile(r"^(?P<mic>[^_]+)_(?P<ts>\d{8}T\d{6})$",  re.IGNORECASE),
]

def parse_name(fname: str):
    p = Path(fname).stem
    for rx in PATTERNS:
        m = rx.match(p)
        if m:
            mic = m.group("mic")
            ts_str = m.group("ts")
            # allow both with/without 'Z'
            fmt = "%Y%m%dT%H%M%SZ" if ts_str.endswith("Z") else "%Y%m%dT%H%M%S"
            ts = datetime.strptime(ts_str, fmt)
            return mic, ts
    return None, None

def window_start_for(ts: datetime) -> datetime:
    bucket_min = (ts.minute // WINDOW_MIN) * WINDOW_MIN
    return ts.replace(minute=bucket_min, second=0, microsecond=0)

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

def apply_delta(slot, delta, sign):
    slot["sum"]           += sign * delta["sum"]
    slot["sum_sq"]        += sign * delta["sum_sq"]
    slot["n"]             += sign * delta["n"]
    slot["active_frames"] += sign * delta["active_frames"]
    slot["total_frames"]  += sign * delta["total_frames"]

def flush_finished_windows(now: datetime, agg):
    finished = []
    for (mic, wstart), s in list(agg.items()):
        if (wstart + timedelta(minutes=WINDOW_MIN)) <= now:
            n = s["n"]
            if n:
                mean = s["sum"] / n
                var  = (s["sum_sq"] / n) - mean**2
                std  = math.sqrt(max(var, 0.0))
                uptime_ratio = s["active_frames"] / s["total_frames"] if s["total_frames"] else 0.0

                # Set REAL metrics
                g_avg_rms.labels(mic).set(mean)
                g_std_rms.labels(mic).set(std)
                g_uptime.labels(mic).set(uptime_ratio)

                # Derived REAL metrics for dashboard
                db = 20.0 * math.log10(max(mean, 1e-12))
                g_volume_db.labels(mic).set(db)
                uptime_seconds = s["active_frames"] * FRAME_SEC
                g_mic_uptime_seconds.labels(mic).set(uptime_seconds)

                print(f"[FLUSH] mic={mic} window={wstart:%Y-%m-%d %H:%M} "
                      f"RMS={mean:.5f} STD={std:.5f} uptime_ratio={uptime_ratio:.3f} "
                      f"db={db:.2f} uptime_sec={uptime_seconds:.2f}")

            finished.append((mic, wstart))
    for key in finished:
        del agg[key]

def main():
    start_http_server(PORT, addr=ADDR)
    print(f"✔ MinIO sound metrics at: http://{ADDR}:{PORT}/metrics")
    client = Minio(MINIO_ENDPOINT, MINIO_ACCESS, MINIO_SECRET, secure=False)

    seen = {}       # fname -> etag
    agg = {}        # (mic, wstart) -> accumulators
    contrib = {}    # fname -> {"wstart": dt, "delta": {...}}

    while True:
        now = now_time()
        # try:
        #     objects = client.list_objects(MINIO_BUCKET, prefix=MINIO_PREFIX, recursive=True)
        # except Exception as e:
        #     print(f"[WARN] list_objects failed: {e}")
        #     time.sleep(10)
        #     continue

        # Iterate all configured prefixes
        for prefix in MINIO_PREFIXES:
            try:
                objects = client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True)
            except Exception as e:
                print(f"[WARN] list_objects failed for prefix={prefix}: {e}")
                time.sleep(5)
                continue

            for obj in objects:
                fname_full = obj.object_name
                fname = Path(fname_full).name
                ext = Path(fname).suffix.lower()
                files_scanned_total.labels(prefix=prefix).inc()
                if ext not in ALLOWED_EXTS:
                    files_skipped_total.labels(prefix=prefix, reason="ext").inc()
                    continue

                etag = getattr(obj, "etag", None)
                if fname in seen and seen[fname] == etag:
                    continue

                mic, ts = parse_name(fname)
                if not mic:
                    files_skipped_total.labels(prefix=prefix, reason="name").inc()
                    # Helpful log once in a while
                    print(f"[SKIP:name] {fname_full} (pattern mismatch)")
                    continue

                resp = None
                try:
                    resp = client.get_object(MINIO_BUCKET, fname_full)
                    data = resp.read()
                except Exception as e:
                    print(f"[ERROR] get_object {fname}: {e}")
                    if resp:
                        try: resp.close(); resp.release_conn()
                        except Exception: pass
                    continue
                finally:
                    if resp:
                        try: resp.close(); resp.release_conn()
                        except Exception: pass

                try:
                    rms, _std, active, total = process_audio_bytes(data, ext)
                except Exception as e:
                    print(f"[ERROR] process_audio {fname}: {e}")
                    continue

                new_wstart = window_start_for(ts)
                new_delta = {
                    "sum": float(rms),
                    "sum_sq": float(rms * rms),
                    "n": 1,
                    "active_frames": int(active),
                    "total_frames": int(total),
                }
                files_parsed_total.labels(prefix=prefix, mic_id=mic).inc()
                
                if fname in contrib:
                    prev = contrib[fname]
                    prev_key = (mic, prev["wstart"])
                    if prev_key in agg:
                        apply_delta(agg[prev_key], prev["delta"], sign=-1)

                key = (mic, new_wstart)
                slot = agg.setdefault(key, {"sum": 0.0, "sum_sq": 0.0, "n": 0,
                                            "active_frames": 0, "total_frames": 0})
                apply_delta(slot, new_delta, sign=+1)

                seen[fname] = etag
                contrib[fname] = {"wstart": new_wstart, "delta": new_delta}
                print(f"[OK] {fname} → mic={mic} RMS={rms:.4f} active={active}/{total} "
                    f"window={new_wstart:%Y-%m-%d %H:%M}")

        flush_finished_windows(now, agg)
        time.sleep(15)

if __name__ == "__main__":
    main()
