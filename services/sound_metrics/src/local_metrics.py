# local_metrics.py
import os, re, time, math
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, soundfile as sf
from prometheus_client import Gauge, start_http_server
import hashlib


AUDIO_DIR   = "audio_samples"
# ADDR, PORT  = "127.0.0.1", 8001
ADDR = os.getenv("ADDR", "0.0.0.0")
PORT = int(os.getenv("PORT", "8001"))
WINDOW_MIN  = 5        #5
FRAME_SEC   = 0.1        
THRESHOLD   = 0.01      
STABLE_SEC  = 5   

ALLOWED_EXTS = {".wav", ".flac", ".ogg", ".aiff", ".aif", ".au", ".mp3", ".m4a", ".aac", ".opus" }

#for local
USE_UTC = False  
def now_time():
    return datetime.utcnow() if USE_UTC else datetime.now()


g_avg_rms = Gauge("sound_avg_volume", "5m avg RMS", ["mic_id"])
g_std_rms = Gauge("sound_std_volume", "5m std of RMS", ["mic_id"])
g_uptime  = Gauge("sound_mic_uptime_ratio", "5m uptime ratio", ["mic_id"])

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
    ts  = datetime.strptime(f"{m.group('date')}_{m.group('h')}-{m.group('m')}", "%Y-%m-%d_%H-%M")
    return mic, ts

def window_start_for(ts: datetime) -> datetime:
    bucket_min = (ts.minute // WINDOW_MIN) * WINDOW_MIN
    return ts.replace(minute=bucket_min, second=0, microsecond=0)

try:
    from pydub import AudioSegment
    HAVE_PYDUB = True
except Exception:
    HAVE_PYDUB = False

FFMPEG_EXTS = {".mp3", ".m4a", ".aac"}

def load_audio(file_path: str):
    ext = Path(file_path).suffix.lower()
    if ext in FFMPEG_EXTS:
        if not HAVE_PYDUB:
            raise RuntimeError(f"pydub (with FFmpeg) is required to read {ext}. Install with: pip install pydub")
        audio = AudioSegment.from_file(file_path)   
        arr = np.array(audio.get_array_of_samples())
        if audio.channels > 1:
            arr = arr.reshape((-1, audio.channels)).mean(axis=1)
        max_int = float(1 << (8 * audio.sample_width - 1))
        samples = (arr.astype(np.float32) / max_int)
        sr = audio.frame_rate
        return samples, sr
    else:
        samples, sr = sf.read(file_path, dtype="float32", always_2d=False)
        if isinstance(samples, np.ndarray) and samples.ndim == 2:
            samples = samples.mean(axis=1)  
        return samples, sr

def process_audio(file_path: str):
    samples, sr = load_audio(file_path)

    rms_all = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0
    std_all = float(np.std(samples)) if samples.size else 0.0

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
    uptime_ratio = (active / total) if total else 0.0
    return rms_all, std_all, active, total

def is_stable(path: Path, min_age_sec: int = STABLE_SEC) -> bool:
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return False
    age = time.time() - mtime
    return age >= min_age_sec

agg = {}

seen = {}  # fname -> {"md5": str}
contrib = {}   # fname -> {"mic": str, "wstart": datetime, "rms": float, "active": int, "total": int}


def flush_finished_windows(now: datetime):
    finished = []
    for (mic, wstart), s in list(agg.items()):
        wend = wstart + timedelta(minutes=WINDOW_MIN)
        if wend <= now:
            n = s["n"]
            if n > 0:
                mean = s["sum"] / n
                var  = (s["sum_sq"] / n) - (mean * mean)
                if var < 0: var = 0.0
                std = math.sqrt(var)
                uptime = (s["active_frames"] / s["total_frames"]) if s["total_frames"] else 0.0

                g_avg_rms.labels(mic).set(mean)
                g_std_rms.labels(mic).set(std)
                g_uptime.labels(mic).set(uptime)
                print(f"[FLUSH] mic={mic} window={wstart:%Y-%m-%d %H:%M} "
                      f"mean_rms={mean:.5f} std={std:.5f} uptime={uptime:.3f}")
            finished.append((mic, wstart))
    for key in finished:
        del agg[key]

def file_md5(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute MD5 checksum for file (chunked)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def main():
    os.makedirs(AUDIO_DIR, exist_ok=True)
    start_http_server(PORT, addr=ADDR)
    print(f"Metrics → http://{ADDR}:{PORT}/metrics")
    print(f"Watching: {Path(AUDIO_DIR).resolve()}")
    if not HAVE_PYDUB:
        print("[INFO] pydub not loaded. MP3/M4A/AAC/WMA require pydub + FFmpeg. Install pydub with: pip install pydub (make sure FFmpeg is installed).")


    loop_counter = 0

    while True:
        now = now_time()

        if loop_counter % 12 == 0 and seen:
            existing = {f for f in seen.keys() if Path(AUDIO_DIR, f).exists()}
            removed = set(seen.keys()) - existing
            for f in removed:
                seen.pop(f, None)
                contrib.pop(f, None)
            if removed:
                print(f"[CLEANUP] removed {len(removed)} entries from caches")

        for fname in os.listdir(AUDIO_DIR):
            p = Path(AUDIO_DIR, fname)
            ext = p.suffix.lower()
            if ext not in ALLOWED_EXTS:
                continue
            if not p.is_file():
                continue

            if not is_stable(p):
                # print(f"[WAIT] not stable yet: {fname}")
                continue

            try:
                curr_md5 = file_md5(p)
            except FileNotFoundError:
                continue

            prev = seen.get(fname)
            changed = (prev is None) or (prev["md5"] != curr_md5)
            if not changed:
                continue 

            mic, ts = parse_name(fname)
            if not mic:
                print(f"[SKIP] bad name format: {fname}")
                continue

            try:
                rms, _std_sample, active, total = process_audio(str(p))
            except Exception as e:
                print(f"[ERROR] Skip {fname}: {e}")
                continue

            wstart = window_start_for(ts)

            old = contrib.get(fname)
            if old:
                old_slot = agg.get((old["mic"], old["wstart"]))
                if old_slot:
                    old_slot["sum"]           -= old["rms"]
                    old_slot["sum_sq"]        -= (old["rms"] * old["rms"])
                    old_slot["n"]             -= 1
                    old_slot["active_frames"] -= old["active"]
                    old_slot["total_frames"]  -= old["total"]
                    if old_slot["n"] <= 0:
                        agg.pop((old["mic"], old["wstart"]), None)

            slot = agg.setdefault(
                (mic, wstart),
                {"sum": 0.0, "sum_sq": 0.0, "n": 0, "active_frames": 0, "total_frames": 0}
            )
            slot["sum"]           += rms
            slot["sum_sq"]        += (rms * rms)
            slot["n"]             += 1
            slot["active_frames"] += active
            slot["total_frames"]  += total

            contrib[fname] = {"mic": mic, "wstart": wstart, "rms": rms, "active": active, "total": total}
            seen[fname]    = {"md5": curr_md5}

            print(f"[OK]{' [UPDATED]' if (prev is not None) else ''} {fname} → mic={mic} "
                  f"win={wstart:%H:%M} rms={rms:.5f} frames={active}/{total}")

        flush_finished_windows(now)
        loop_counter += 1
        time.sleep(5)


if __name__ == "__main__":
    main()
