"""
Smoke E2E test for the classify CLI.

This test:
- Generates a short mono WAV (16-bit PCM, 32kHz, 0.5s).
- Loads environment variables from 'classification/.env'.
- Requires TEST_CHECKPOINT env var (path to a checkpoint). If missing, the test is skipped.
- Optionally reads TEST_DEVICE (default: "cpu").
- Runs scripts.classify.main() on the generated WAV and expects a normal exit
  (SystemExit with code 0 or no exception raised).
"""
import os
import wave
import struct
import math
from pathlib import Path

import pytest
from dotenv import load_dotenv  # pip install python-dotenv

# Import the CLI module under test (assumes PYTHONPATH is configured so that "scripts" package/module is importable)
from scripts import classify as CL


# -------------------- load env --------------------
env_path = Path(__file__).parents[2] / ".env"  # ../../.env from this test file
if env_path.exists():
    load_dotenv(dotenv_path=env_path)


def _write_sine_wav(path: Path, sr: int = 32000, freq: float = 440.0, duration_s: float = 0.5, amplitude: float = 0.3):
    """Write a small mono WAV with a sine tone (16-bit PCM)."""
    n_frames = int(sr * duration_s)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sr)
        for i in range(n_frames):
            sample = amplitude * math.sin(2.0 * math.pi * freq * (i / sr))
            val = max(-1.0, min(1.0, sample))
            wf.writeframes(struct.pack("<h", int(val * 32767)))


def test_classify_cli_smoke(tmp_path):
    """
    Run classify.main() on a single small WAV and expect SystemExit(0) or normal return.
    Skip if TEST_CHECKPOINT is not set in the environment.
    """
    ckpt = os.getenv("TEST_CHECKPOINT", "").strip()
    if not ckpt:
        pytest.skip("Missing TEST_CHECKPOINT; skipping smoke E2E test.")

    device = os.getenv("TEST_DEVICE", "cpu").strip() or "cpu"

    wav = tmp_path / "smoke.wav"
    _write_sine_wav(wav, sr=32000, freq=440.0, duration_s=0.5)

    argv = [
        "classify.py",
        "--audio", str(wav),
        "--checkpoint", ckpt,
        "--device", device,
        "--window-sec", "0.5",
        "--hop-sec", "0.5",
    ]

    CL.sys.argv = argv
    try:
        CL.main()
    except SystemExit as e:
        # Accept explicit successful exit
        assert e.code == 0
