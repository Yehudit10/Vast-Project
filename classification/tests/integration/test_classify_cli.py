"""
Integration-like tests for scripts/classify.py (no real DB, no heavy models).

We patch all heavy or external dependencies:
- ensure_checkpoint -> returns a local path
- AudioTagging -> dummy class
- load_audio / segment_waveform -> synthetic wave
- run_inference / run_inference_with_embedding -> deterministic arrays
- aggregate_matrix -> fixed aggregation
- joblib.load -> dummy head with predict_proba and classes_
- db_io_pg -> fake module (for the with-DB test)
"""

from pathlib import Path
import numpy as np
import pytest
from types import SimpleNamespace

# Import module under test (run pytest from classification with PYTHONPATH=$PWD)
from scripts import classify as CL


# ----------------------- Helpers -----------------------

def _mk_two_wavs(tmp_path: Path):
    """Create two tiny wav placeholders under tmp_path and return their paths."""
    p1 = tmp_path / "a.wav"; p2 = tmp_path / "b.wav"
    p1.write_bytes(b"RIFF....WAVE")
    p2.write_bytes(b"RIFF....WAVE")
    return str(p1), str(p2)

def _patch_model_stack(monkeypatch, ckpt_path: Path, emb_dim: int = 6, n_classes: int = 4):
    """Patch model/audio functions and return the dummy head class used by joblib.load."""
    # ensure checkpoint path is accepted as-is
    monkeypatch.setattr(CL, "ensure_checkpoint", lambda p, checkpoint_url=None: str(ckpt_path), raising=True)

    # AudioTagging dummy (ctor signature flexible)
    class DummyAT:
        def __init__(self, *a, **k): pass
    monkeypatch.setattr(CL, "AudioTagging", DummyAT, raising=True)

    # audio loader / segmentation
    sr = 32000
    wav = np.zeros(int(0.5 * sr), dtype=np.float32)  # 0.5s
    monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
    # single window [0,0.5)
    monkeypatch.setattr(CL, "segment_waveform",
                        lambda y, sr, window_sec, hop_sec, pad_last:
                            [(0.0, 0.5, y)], raising=True)

    # inference / embedding (choose one of them as used by your code)
    clip = np.array([0.2, 0.1, 0.6, 0.1], dtype=np.float32)[:n_classes]
    emb  = np.arange(emb_dim, dtype=np.float32)
    monkeypatch.setattr(CL, "run_inference", lambda at, seg: (clip, ["animal","vehicle","shotgun","other"][:n_classes]), raising=False)
    monkeypatch.setattr(CL, "run_inference_with_embedding",
                        lambda at, seg: (clip, ["animal","vehicle","shotgun","other"][:n_classes], emb),
                        raising=False)

    # aggregation (over windows) -> identity on clip/mean on stack
    monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)

    # dummy head: predict_proba returns fixed [p_animal, p_vehicle, p_shotgun, p_other]
    class DummyHead:
        def __init__(self):
            self.classes_ = np.array(["animal","vehicle","shotgun","other"][:n_classes])
        def predict_proba(self, X):
            X = np.asarray(X)
            # Return probabilities to match classes_
            base = np.array([[0.7, 0.2, 0.05, 0.05][:n_classes]], dtype=np.float32)
            return np.repeat(base, X.shape[0], axis=0)
    monkeypatch.setattr(CL.joblib, "load", lambda path: DummyHead(), raising=True)
    return DummyHead


def _try_argvs_and_run(monkeypatch, base_argv_list):
    """
    Some projects name arguments differently. Try a few common variants until one passes.
    We assume classify.main() will raise SystemExit(2) on bad args; we keep trying.
    """
    for argv in base_argv_list:
        monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
        try:
            CL.main()
            return argv  # success
        except SystemExit as e:
            # argparse error -> try next variant
            if e.code == 2:
                continue
            # any other exit we re-raise
            raise
    raise AssertionError("No argv variant matched your CLI. Please adjust the candidates in the test.")


# ----------------------- Tests -----------------------

def test_classify_cli_no_db(monkeypatch, tmp_path, capsys):
    """
    End-to-end classify without touching DB:
    - Build two input wav paths
    - Patch model/embedding/head stack
    - Run CLI with several argv candidates (paths/inputs/glob)
    - Assert output contains per-file results and head predictions
    """
    # inputs & checkpoint
    w1, w2 = _mk_two_wavs(tmp_path)
    ckpt = tmp_path / "ckpt.bin"
    ckpt.write_bytes(b"ckpt")

    # patch heavy deps
    _ = _patch_model_stack(monkeypatch, ckpt)

    # Try a few CLI variants common in projects (pick the one that fits your argparse)
    base = [
        # 1) explicit --paths
        ["classify.py", "--paths", w1, w2, "--checkpoint", str(ckpt), "--device", "cpu"],
        # 2) comma-separated --inputs
        ["classify.py", "--inputs", f"{w1},{w2}", "--checkpoint", str(ckpt), "--device", "cpu"],
        # 3) positional
        ["classify.py", w1, w2, "--checkpoint", str(ckpt), "--device", "cpu"],
        # 4) glob
        ["classify.py", "--glob", str(tmp_path / "*.wav"), "--checkpoint", str(ckpt), "--device", "cpu"],
    ]
    used_argv = _try_argvs_and_run(monkeypatch, base)

    out = capsys.readouterr().out.lower()

    # Minimal assertions: file names appear and we see class names / probabilities
    assert Path(w1).name.lower() in out
    assert Path(w2).name.lower() in out

    # Expect our dummy head distribution somewhere
    # (We don't tie to exact formatting to keep the test robust)
    for cls in ("animal","vehicle","shotgun","other"):
        assert (cls in out) or (cls[:3] in out)  # accept abbreviated formatting


def test_classify_cli_with_fake_db(monkeypatch, tmp_path):
    """
    Run classify with a fake db_io_pg module injected into CL, ensuring
    the flow: open_db -> upsert_run -> (per file: upsert_file, upsert_file_aggregate) -> finish_run.
    """
    w1, w2 = _mk_two_wavs(tmp_path)
    ckpt = tmp_path / "ckpt.bin"; ckpt.write_bytes(b"ckpt")
    _ = _patch_model_stack(monkeypatch, ckpt)

    # record calls
    calls = {"open_db": 0, "upsert_run": 0, "finish_run": 0, "upsert_file": [], "upsert_file_aggregate": []}

    def fake_open_db(db_url, schema="audio_cls"):
        calls["open_db"] += 1
        return SimpleNamespace(closed=False)

    def fake_upsert_run(conn, meta):
        calls["upsert_run"] += 1

    def fake_finish_run(conn, run_id):
        calls["finish_run"] += 1

    def fake_upsert_file(conn, path, duration_s, sample_rate, size_bytes=None):
        # return deterministic id per path
        fid = 1 if path.endswith("a.wav") else 2
        calls["upsert_file"].append((path, fid))
        return fid

    def fake_upsert_file_aggregate(conn, row):
        calls["upsert_file_aggregate"].append(row)

    fake_db = SimpleNamespace(
        open_db=fake_open_db,
        upsert_run=fake_upsert_run,
        finish_run=fake_finish_run,
        upsert_file=fake_upsert_file,
        upsert_file_aggregate=fake_upsert_file_aggregate,
    )
    # inject fake db module into classify
    monkeypatch.setattr(CL, "db_io_pg", fake_db, raising=True)

    # Try a few CLI variants that include DB URL / schema flags commonly used
    base = [
        ["classify.py", "--paths", w1, w2, "--checkpoint", str(ckpt), "--device", "cpu",
         "--db-url", "postgres://u:p@h:5432/db", "--schema", "audio_cls"],
        ["classify.py", "--inputs", f"{w1},{w2}", "--checkpoint", str(ckpt), "--device", "cpu",
         "--db-url", "postgres://u:p@h:5432/db", "--schema", "audio_cls"],
        [ "classify.py", w1, w2, "--checkpoint", str(ckpt), "--device", "cpu",
          "--db-url", "postgres://u:p@h:5432/db", "--schema", "audio_cls"],
        ["classify.py", "--glob", str(tmp_path/"*.wav"), "--checkpoint", str(ckpt), "--device", "cpu",
         "--db-url", "postgres://u:p@h:5432/db", "--schema", "audio_cls"],
    ]
    _ = _try_argvs_and_run(monkeypatch, base)

    # Verify DB flow occurred
    assert calls["open_db"] == 1
    assert calls["upsert_run"] >= 1
    assert calls["finish_run"] == 1
    # Should have inserted both files
    paths_seen = sorted(p for p,_fid in calls["upsert_file"])
    assert paths_seen == sorted([w1, w2])
    # And at least one aggregate row per file
    fids = sorted(r["file_id"] for r in calls["upsert_file_aggregate"])
    assert fids == [1, 2]
