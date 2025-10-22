import pytest
from pathlib import Path
import numpy as np
import scripts.train_head as TH

def test_discover_labeled_files_ignores_non_audio(tmp_path: Path):
    root = tmp_path
    classes = TH.DEFAULT_CLASSES[:4]

    for cls in classes:
        (root / cls).mkdir(parents=True, exist_ok=True)

    # audio file
    (root / "predatory_animals" / "a.wav").write_bytes(b"RIFF....WAVE")

    # non-audio file
    (root / "vehicle").mkdir(parents=True, exist_ok=True)
    (root / "vehicle" / "readme.txt").write_text("ignore me", encoding="utf-8")

    files = TH.discover_labeled_files(root, classes)

    # ensure non-audio files are ignored
    for fpath, _ in files:
        assert fpath.suffix.lower() in [".wav", ".mp3", ".flac"]


def test_main_dry_run_with_mocks(monkeypatch, tmp_path: Path, capsys):
    root = tmp_path / "data"
    out_dir = tmp_path / "out"
    ckpt = tmp_path / "ckpt.bin"
    classes = TH.DEFAULT_CLASSES[:4]

    # create audio files
    for cls, fname in zip(classes, ["a.wav", "v.wav", "s.wav", "o.wav"]):
        d = root / cls
        d.mkdir(parents=True, exist_ok=True)
        (d / fname).write_bytes(b"RIFF....WAVE")

    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt.write_bytes(b"fake_checkpoint")

    # --- mocks ---
    monkeypatch.setattr(TH, "_embed_clip", lambda backbone, at, wav, device, ast_dir: np.arange(8, dtype=np.float32))
    monkeypatch.setattr(TH, "AudioTagging", lambda *a, **k: None)
    monkeypatch.setattr(TH, "load_audio", lambda path, target_sr: np.zeros(160, dtype=np.float32))
    monkeypatch.setattr(TH.joblib, "dump", lambda obj, path: Path(path).write_bytes(b"pipeline"))

    # mock load_cnn14_model to avoid torch.load
    monkeypatch.setattr(TH, "load_cnn14_model", lambda ckpt, url=None, device="cpu": None)

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
    monkeypatch.setattr(TH.sys, "argv", argv, raising=False)
    monkeypatch.setenv("PYTHONHASHSEED", "0")

    # run main (dry-run)
    TH.main()

    # check that output files were "written"
    assert out_head.exists()
    assert out_meta.exists()
