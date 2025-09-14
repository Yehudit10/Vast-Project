"""
Unit tests for scripts/train_head.py

Focus:
- discover_labeled_files: finds labeled audio files under class subfolders
- (optional) env_bool: robust parsing of boolean-like strings
- main() dry-run: full CLI flow with mocks for heavy parts (no real training/model)
"""

import json
import os
from pathlib import Path
import numpy as np
import pytest

# Import under test (assuming pytest is run from classification/ with PYTHONPATH=$PWD)
from scripts import train_head as TH


# ----------------------- discover_labeled_files -----------------------

def test_discover_labeled_files_basic(tmp_path: Path):
    """
    Create a tiny dataset tree:
      root/
        animal/a.wav
        vehicle/v.wav
        shotgun/s.wav
        other/o.wav
        noise/ignored.wav   (unknown class -> should be ignored)
    Expect (label, path) pairs for the 4 known classes only.
    """
    root = tmp_path
    classes = ["animal", "vehicle", "shotgun", "other"]

    # Build tree & files
    for cls, fname in zip(classes, ["a.wav", "v.wav", "s.wav", "o.wav"]):
        d = root / cls
        d.mkdir(parents=True, exist_ok=True)
        (d / fname).write_bytes(b"RIFF....WAVE")  # header placeholder; function only checks extension

    # Unknown class folder should be ignored:
    (root / "noise").mkdir()
    (root / "noise" / "ignored.wav").write_bytes(b"RIFF....WAVE")

    pairs = TH.discover_labeled_files(root, classes)

    # Normalize to sets to be order-agnostic
    got = {(lbl, Path(p)) for lbl, p in pairs}
    exp = {
        ("animal", (root / "animal" / "a.wav")),
        ("vehicle", (root / "vehicle" / "v.wav")),
        ("shotgun", (root / "shotgun" / "s.wav")),
        ("other", (root / "other" / "o.wav")),
    }
    assert got == exp


def test_discover_labeled_files_ignores_non_audio(tmp_path: Path):
    """
    Ensure non-audio extensions in class folders are ignored.
    """
    root = tmp_path
    classes = ["animal", "vehicle", "shotgun", "other"]

    (root / "animal").mkdir()
    (root / "vehicle").mkdir()
    (root / "shotgun").mkdir()
    (root / "other").mkdir()

    # Valid audio
    (root / "animal" / "a.wav").write_bytes(b"RIFF....WAVE")
    # Non-audio should be ignored
    (root / "vehicle" / "readme.txt").write_text("ignore me", encoding="utf-8")

    pairs = TH.discover_labeled_files(root, classes)
    got = {(lbl, Path(p)) for lbl, p in pairs}
    assert ("animal", root / "animal" / "a.wav") in got
    assert all("readme.txt" not in str(p) for _lbl, p in pairs)


# ----------------------- env_bool (optional) -----------------------

@pytest.mark.skipif(not hasattr(TH, "env_bool"), reason="env_bool() not present in train_head")
def test_env_bool_parsing_minimal():
    """
    Project-agnostic assertions:
    - Canonical falsy tokens must map to False.
    - The function returns a bool for any string (no exceptions).
    - Case-insensitivity: lower/upper yield same result.
    """
    falsy_tokens = ["false", "FALSE", "no", "off", "0", ""]
    for tok in falsy_tokens:
        assert TH.env_bool(tok) is False

    # Non-failing and boolean return type for various tokens (truthy handling is implementation-specific)
    for tok in ["true", "TRUE", "yes", "on", "1", "maybe", "random"]:
        out = TH.env_bool(tok)
        assert isinstance(out, bool)
        # case-insensitive behavior
        assert out == TH.env_bool(tok.lower()) == TH.env_bool(tok.upper())

# ----------------------- main() dry run with mocks -----------------------

def test_main_dry_run_with_mocks(monkeypatch, tmp_path: Path, capsys):
    """
    Run train_head.main() end-to-end with a tiny synthetic dataset and mocks:
    - ensure_checkpoint: returns a checkpoint path without network
    - AudioTagging: dummy class whose embedding is deterministic
    - load_audio: returns a zero waveform
    - run_embedding: returns fixed-size embedding vector
    - joblib.dump: writes a small file (pipeline), verified to exist
    - meta.json: saved with expected fields (class_order, seed, test_size, etc.)
    """
    root = tmp_path / "data"
    out_dir = tmp_path / "out"
    ckpt = tmp_path / "ckpt.bin"
    classes = ["animal", "vehicle", "shotgun", "other"]

    # dataset
    for cls, fname in zip(classes, ["a.wav", "v.wav", "s.wav", "o.wav"]):
        d = root / cls
        d.mkdir(parents=True, exist_ok=True)
        (d / fname).write_bytes(b"RIFF....WAVE")

    # make sure output dir exists or will be created by the script
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt.write_bytes(b"ckpt")  # just to have a real file path

    # --- mocks ---

    # ensure_checkpoint: return the same path without any download/check
    monkeypatch.setattr(TH, "ensure_checkpoint", lambda p, checkpoint_url=None: str(ckpt))

    # Dummy AudioTagging with a stable embedding size
    class DummyAT:
        def __init__(self, *a, **k): pass
    monkeypatch.setattr(TH, "AudioTagging", DummyAT, raising=True)

    # load_audio: return a short waveform (will be embedded)
    monkeypatch.setattr(TH, "load_audio", lambda path, target_sr: np.zeros(160, dtype=np.float32))

    # run_embedding: fixed-length embedding vector
    emb_dim = 8
    monkeypatch.setattr(TH, "run_embedding", lambda at, wav: np.arange(emb_dim, dtype=np.float32))

    # joblib.dump: actually write something small so we can assert the file exists
    saved = {}
    def fake_dump(obj, path):
        Path(path).write_bytes(b"pipeline")
        saved["path"] = str(path)
    monkeypatch.setattr(TH.joblib, "dump", fake_dump)

    # --- run CLI main() ---

    out_head = out_dir / "head.joblib"
    out_meta = out_dir / "meta.json"

    argv = [
        "train_head.py",
        "--train-dir", str(root),
        "--checkpoint", str(ckpt),
        "--device", "cpu",
        "--classes", ",".join(classes),
        "--test-size", "0.5",
        "--seed", "0",
        "--out", str(out_head),
        "--meta", str(out_meta),
    ]
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    monkeypatch.setattr(TH.sys, "argv", argv, raising=False)

    # Call main
    TH.main()

    # --- asserts on outputs ---

    assert out_head.exists(), "head.joblib should be written"
    assert out_meta.exists(), "meta.json should be written"
    assert saved.get("path") == str(out_head)

    meta = json.loads(out_meta.read_text(encoding="utf-8"))
    assert meta.get("class_order") == classes
    assert meta.get("seed") in (0, "0")
    assert float(meta.get("test_size")) == 0.5
    assert Path(meta.get("checkpoint")).name == ckpt.name
    assert meta.get("device") == "cpu"

    # Ensure CLI printed something informative (not strictly required)
    captured = capsys.readouterr()
    # No strict content checks to avoid coupling; just ensure no error message
    assert "[error]" not in captured.out.lower()
