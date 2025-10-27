import os
import time
from pathlib import Path
from datetime import datetime
import numpy as np
import soundfile as sf
import importlib
import types
import math
import builtins

import local_metrics as lm


def test_parse_name_valid_and_invalid():
    mic, ts = lm.parse_name("micA_2025-09-14_12-34.wav")
    assert mic == "micA"
    assert ts.year == 2025 and ts.month == 9 and ts.day == 14 and ts.hour == 12 and ts.minute == 34

    mic2, ts2 = lm.parse_name("badname.wav")
    assert mic2 is None and ts2 is None


def test_window_start_for_respects_5min_buckets(monkeypatch):
    monkeypatch.setattr(lm, "WINDOW_MIN", 5)
    t = datetime(2025, 9, 14, 12, 7, 55)
    ws = lm.window_start_for(t)
    assert ws.minute == 5 and ws.second == 0 and ws.microsecond == 0

    t2 = datetime(2025, 9, 14, 12, 0, 1)
    ws2 = lm.window_start_for(t2)
    assert ws2.minute == 0 and ws2.second == 0


def test_is_stable(tmp_path, monkeypatch):
    p = tmp_path / "a.wav"
    p.write_bytes(b"\x00\x00")
    monkeypatch.setattr(lm, "STABLE_SEC", 5)
    assert not lm.is_stable(p, min_age_sec=5)
    old = time.time() - 10
    os.utime(p, (old, old))
    assert lm.is_stable(p, min_age_sec=5)


def _write_wav(path: Path, seconds=1.0, sr=16000, freq=440.0, amplitude=0.1, stereo=False):
    t = np.arange(int(sr*seconds), dtype=np.float32) / sr
    wave = amplitude * np.sin(2*np.pi*freq*t).astype(np.float32)
    if stereo:
        wave = np.stack([wave, wave], axis=1)
    sf.write(str(path), wave, sr)
    return wave, sr


def test_process_audio_silence_vs_tone(tmp_path, monkeypatch):
    monkeypatch.setattr(lm, "FRAME_SEC", 0.1)
    monkeypatch.setattr(lm, "THRESHOLD", 0.01)  # ≈ -40 dBFS

    p_sil = tmp_path / "mic1_2025-09-14_12-00.wav"
    sf.write(str(p_sil), np.zeros(16000, dtype=np.float32), 16000)
    rms, std, active, total = lm.process_audio(str(p_sil))
    assert math.isclose(rms, 0.0, abs_tol=1e-7)
    assert active == 0 and total > 0

    p_tone = tmp_path / "mic1_2025-09-14_12-05.wav"
    _wave, _sr = _write_wav(p_tone, seconds=1.0, sr=16000, freq=440.0, amplitude=0.1)
    rms2, std2, active2, total2 = lm.process_audio(str(p_tone))
    assert rms2 > 0.03  
    assert active2 > 0 and total2 > 0
    assert active2 / total2 > 0.8


class _FakeGauge:
    def __init__(self):
        self.values = {}  # (label,) -> last_set_value
    def labels(self, mic_id):
        class _Setter:
            def __init__(self, outer, key):
                self.outer = outer
                self.key = key
            def set(self, v):
                self.outer.values[self.key] = v
        return _Setter(self, (mic_id,))


def test_aggregation_and_flush(tmp_path, monkeypatch):
    monkeypatch.setattr(lm, "start_http_server", lambda *a, **k: None)

    lm.agg.clear()
    lm.seen.clear()
    lm.contrib.clear()

    fake_avg = _FakeGauge()
    fake_std = _FakeGauge()
    fake_up = _FakeGauge()
    monkeypatch.setattr(lm, "g_avg_rms", fake_avg)
    monkeypatch.setattr(lm, "g_std_rms", fake_std)
    monkeypatch.setattr(lm, "g_uptime", fake_up)

    monkeypatch.setattr(lm, "AUDIO_DIR", str(tmp_path))
    monkeypatch.setattr(lm, "WINDOW_MIN", 5)
    monkeypatch.setattr(lm, "FRAME_SEC", 0.1)
    monkeypatch.setattr(lm, "THRESHOLD", 0.01)

    f1 = tmp_path / "micA_2025-09-14_12-01.wav"
    _write_wav(f1, seconds=1.0, amplitude=0.1)
    f2 = tmp_path / "micA_2025-09-14_12-04.wav"
    _write_wav(f2, seconds=1.0, amplitude=0.05)

    monkeypatch.setattr(lm, "file_md5", lambda p: Path(p).read_bytes().__hash__().__repr__())

    for fname in os.listdir(lm.AUDIO_DIR):
        p = Path(lm.AUDIO_DIR, fname)
        if p.suffix.lower() not in lm.ALLOWED_EXTS or not p.is_file():
            continue

        if not lm.is_stable(p, min_age_sec=0):
            continue

        curr_md5 = lm.file_md5(p)
        prev = lm.seen.get(fname)
        changed = (prev is None) or (prev["md5"] != curr_md5)
        if not changed:
            continue

        mic, ts = lm.parse_name(fname)
        assert mic and ts
        rms, _std, active, total = lm.process_audio(str(p))
        wstart = lm.window_start_for(ts)

        old = lm.contrib.get(fname)
        if old:
            old_slot = lm.agg.get((old["mic"], old["wstart"]))
            if old_slot:
                old_slot["sum"]           -= old["rms"]
                old_slot["sum_sq"]        -= old["rms"] * old["rms"]
                old_slot["n"]             -= 1
                old_slot["active_frames"] -= old["active"]
                old_slot["total_frames"]  -= old["total"]
                if old_slot["n"] <= 0:
                    lm.agg.pop((old["mic"], old["wstart"]), None)

        slot = lm.agg.setdefault((mic, wstart),
                                 {"sum": 0.0, "sum_sq": 0.0, "n": 0,
                                  "active_frames": 0, "total_frames": 0})
        slot["sum"]           += rms
        slot["sum_sq"]        += rms * rms
        slot["n"]             += 1
        slot["active_frames"] += active
        slot["total_frames"]  += total

        lm.contrib[fname] = {"mic": mic, "wstart": wstart, "rms": rms,
                             "active": active, "total": total}
        lm.seen[fname] = {"md5": curr_md5}

    lm.flush_finished_windows(datetime(2025, 9, 14, 12, 6, 0))

    assert ("micA",) in fake_avg.values
    mean_rms = fake_avg.values[("micA",)]
    std_rms  = fake_std.values[("micA",)]
    uptime   = fake_up.values[("micA",)]
    assert 0.02 < mean_rms < 0.09
    assert std_rms >= 0.0
    assert 0.0 <= uptime <= 1.0

