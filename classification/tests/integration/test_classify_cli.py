# classification/tests/integration/test_classify_cli.py
"""
Integration-like tests for scripts/classify.py (no real DB, no heavy models).

We patch all heavy or external dependencies:
- ensure_checkpoint -> returns a local path
- AudioTagging -> dummy class
- load_audio / segment_waveform -> synthetic wave
- run_inference / run_inference_with_embedding -> deterministic arrays
- aggregate_matrix -> fixed aggregation
- joblib.load -> dummy head with predict_proba and classes_
- db_io_pg -> fake (for the DB-flow test)
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
    """
    Patch model/audio functions and return the dummy head class used by joblib.load.
    This keeps the classify pipeline fast and deterministic.
    """
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

    # aggregation (over windows) -> mean over rows
    monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)

    # dummy head: predict_proba returns fixed [p_animal, p_vehicle, p_shotgun, p_other]
    class DummyHead:
        def __init__(self):
            self.classes_ = np.array(["animal","vehicle","shotgun","other"][:n_classes])
        def predict_proba(self, X):
            X = np.asarray(X)
            base = np.array([[0.7, 0.2, 0.05, 0.05][:n_classes]], dtype=np.float32)
            return np.repeat(base, X.shape[0], axis=0)

    # Patch joblib.load on the real joblib module (classify may import it inside main)
    import joblib as _joblib
    monkeypatch.setattr(_joblib, "load", lambda path: DummyHead(), raising=True)

    return DummyHead


# ----------------------- Tests -----------------------

def test_classify_cli_no_db(monkeypatch, tmp_path, capsys):
    """
    End-to-end classify on two separate invocations (since CLI expects a single --audio).
    No DB. We patch model/embedding/head stack and assert outputs contain filenames & classes.
    """
    # inputs & checkpoint
    w1, w2 = _mk_two_wavs(tmp_path)
    ckpt = tmp_path / "ckpt.bin"
    ckpt.write_bytes(b"ckpt")

    # patch heavy deps
    _ = _patch_model_stack(monkeypatch, ckpt)

    def run_once(wav_path: str):
        argv = ["classify.py", "--audio", wav_path, "--checkpoint", str(ckpt), "--device", "cpu"]
        monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
        CL.main()
        return capsys.readouterr().out.lower()

    out1 = run_once(w1)
    out2 = run_once(w2)
    out  = out1 + "\n" + out2

    # file names appear
    assert Path(w1).name.lower() in out
    assert Path(w2).name.lower() in out

    # Expect our dummy head distribution somewhere (don’t force exact formatting)
    for cls in ("animal", "vehicle", "shotgun", "other"):
        assert (cls in out) or (cls[:3] in out)


def test_classify_cli_with_fake_db(monkeypatch, tmp_path):
    """
    Invoke classify twice (one file per run) with a fake core.db_io_pg injected.
    We verify the DB flow and that both files were upserted + aggregated.
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
        # deterministic id per path name
        fid = 1 if path.endswith("a.wav") else 2
        calls["upsert_file"].append((path, fid))
        return fid

    def fake_upsert_file_aggregate(conn, row):
        calls["upsert_file_aggregate"].append(row)

    # Patch the actual module used by classify: "from core import db_io_pg"
    import core.db_io_pg as dbmod
    monkeypatch.setattr(dbmod, "open_db",               fake_open_db,               raising=True)
    monkeypatch.setattr(dbmod, "upsert_run",            fake_upsert_run,            raising=True)
    monkeypatch.setattr(dbmod, "finish_run",            fake_finish_run,            raising=True)
    monkeypatch.setattr(dbmod, "upsert_file",           fake_upsert_file,           raising=True)
    monkeypatch.setattr(dbmod, "upsert_file_aggregate", fake_upsert_file_aggregate, raising=True)

    def run_once(wav_path: str):
        argv = [
            "classify.py",
            "--audio", wav_path,
            "--checkpoint", str(ckpt),
            "--device", "cpu",
            "--write-db",
            "--db-url", "postgres://u:p@h:5432/db",
            "--db-schema", "audio_cls",
        ]
        monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
        CL.main()

    # Run twice (one file per invocation)
    run_once(w1)
    run_once(w2)

    # Verify DB flow occurred (twice for two files)
    assert calls["open_db"] >= 1          # could be 1 or 2 depending on implementation
    assert calls["upsert_run"] >= 1
    assert calls["finish_run"] >= 1

    # Should have inserted both files
    paths_seen = sorted(p for p, _fid in calls["upsert_file"])
    assert paths_seen == sorted([w1, w2])

    # And at least one aggregate row per file
    fids = sorted(r["file_id"] for r in calls["upsert_file_aggregate"])
    assert fids == [1, 2]

def _patch_light_stack(monkeypatch):
    """
    Minimal patch so CLI can run without heavy model loading:
    - ensure_checkpoint: accept any path (create tiny placeholder if needed)
    - AudioTagging: dummy
    - load_audio / segment_waveform: one short window
    - run_inference / run_inference_with_embedding: deterministic outputs
    - aggregate_matrix: mean
    """
    import numpy as np
    import pathlib as _pl

    def _fake_ensure_checkpoint(p, checkpoint_url=None):
        p = _pl.Path(p if p else "ckpt.bin"); p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists(): p.write_bytes(b"stub")
        return str(p)
    monkeypatch.setattr(CL, "ensure_checkpoint", _fake_ensure_checkpoint, raising=True)

    class DummyAT:
        def __init__(self, *a, **k): pass
    monkeypatch.setattr(CL, "AudioTagging", DummyAT, raising=True)

    sr = 32000
    wav = np.zeros(int(0.5*sr), dtype=np.float32)
    monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
    monkeypatch.setattr(CL, "segment_waveform", lambda y, sr, window_sec, hop_sec, pad_last: [(0.0, 0.5, y)], raising=True)

    clip = np.array([0.2,0.1,0.6,0.1], dtype=np.float32)
    emb  = np.arange(8, dtype=np.float32)
    monkeypatch.setattr(CL, "run_inference", lambda at, seg: (clip, ["animal","vehicle","shotgun","other"]), raising=False)
    monkeypatch.setattr(CL, "run_inference_with_embedding",
                        lambda at, seg: (clip, ["animal","vehicle","shotgun","other"], emb), raising=False)
    monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)


def test_cli_requires_audio_exits_2(monkeypatch):
    """
    Missing --audio should trigger argparse usage and exit code 2.
    """
    monkeypatch.setattr(CL.sys, "argv", ["classify.py"], raising=False)
    with pytest.raises(SystemExit) as e:
        CL.main()
    assert e.value.code == 2


def test_cli_unsupported_extension_exits_4(tmp_path: Path, monkeypatch):
    """
    Passing a file with unsupported extension should exit(4).
    """
    bad = tmp_path / "bad.txt"
    bad.write_text("not audio")
    argv = ["classify.py", "--audio", str(bad)]
    monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
    with pytest.raises(SystemExit) as e:
        CL.main()
    assert e.value.code == 4


def test_cli_pad_flags_and_print_windows(monkeypatch, tmp_path: Path):
    """
    Smoke test: ensure --pad-last/--no-pad-last and --print-windows go through the pipeline.
    We patch the heavy stack so the CLI runs fast and deterministically.
    """
    _patch_light_stack(monkeypatch)
    wav = tmp_path / "ok.wav"
    # quick valid WAV
    import wave, struct, math
    sr = 32000; n = int(sr*0.5)
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        for i in range(n):
            sample = 0.25*math.sin(2*math.pi*440*(i/sr))
            wf.writeframes(struct.pack("<h", int(max(-1,min(1,sample))*32767)))

    # --pad-last
    argv = [
        "classify.py", "--audio", str(wav),
        "--checkpoint", str(tmp_path/"ckpt.bin"),
        "--device", "cpu",
        "--window-sec", "0.5",
        "--hop-sec", "0.5",
        "--pad-last",
        "--print-windows",
    ]
    monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
    CL.main()  # should not raise

    # --no-pad-last
    argv2 = [
        "classify.py", "--audio", str(wav),
        "--checkpoint", str(tmp_path/"ckpt2.bin"),
        "--device", "cpu",
        "--window-sec", "0.5",
        "--hop-sec", "0.5",
        "--no-pad-last",
        "--print-windows",
    ]
    monkeypatch.setattr(CL.sys, "argv", argv2, raising=False)
    CL.main()  # should not raise

def test_cli_rejects_non_positive_window_or_hop(monkeypatch, tmp_path: Path):
    from scripts import classify as CL
    wav = tmp_path / "a.wav"; wav.write_bytes(b"RIFF....WAVE")

    # window<=0
    argv = ["classify.py", "--audio", str(wav), "--window-sec", "0", "--hop-sec", "0.5"]
    monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
    with pytest.raises(SystemExit) as e:
        CL.main()
    assert e.value.code == 2

    # hop<=0
    argv = ["classify.py", "--audio", str(wav), "--window-sec", "0.5", "--hop-sec", "0"]
    monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
    with pytest.raises(SystemExit) as e:
        CL.main()
    assert e.value.code == 2

def test_cli_accepts_directory_input(monkeypatch, tmp_path: Path):
    from scripts import classify as CL
    d = tmp_path / "dir"; d.mkdir()
    (d / "x.wav").write_bytes(b"RIFF....WAVE")

    # Patch heavy stack quickly
    def fake_ensure(p, checkpoint_url=None): Path(p or (tmp_path/"ckpt.bin")).write_bytes(b"stub"); return str(tmp_path/"ckpt.bin")
    monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure, raising=True)
    monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}), raising=True)
    import numpy as np
    wav = np.zeros(16000, dtype=np.float32)
    monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
    monkeypatch.setattr(CL, "segment_waveform", lambda y,sr,w,h,p: [(0.0, 0.5, y)], raising=True)
    monkeypatch.setattr(CL, "run_inference", lambda at, seg: (np.array([0.2,0.1,0.6,0.1], dtype=np.float32), ["animal","vehicle","shotgun","other"]), raising=False)
    monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)

    argv = ["classify.py", "--audio", str(d), "--checkpoint", str(tmp_path/"ckpt.bin"), "--device", "cpu",
            "--window-sec", "0.5", "--hop-sec", "0.5", "--pad-last"]
    monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
    CL.main()  # should process the file in directory

def test_cli_warns_when_hop_greater_than_window(monkeypatch, tmp_path: Path, caplog):
    """
    When --hop-sec > --window-sec, CLI should warn but still proceed.
    """
    from scripts import classify as CL

    # תיקון קל לערימה הכבדה – ממש מינימלי
    def fake_ensure(p, checkpoint_url=None):
        Path(p or (tmp_path/"ckpt.bin")).write_bytes(b"stub")
        return str(p or (tmp_path/"ckpt.bin"))
    monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure, raising=True)
    monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}), raising=True)

    import numpy as np
    wav = np.zeros(16000, dtype=np.float32)
    monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
    monkeypatch.setattr(CL, "segment_waveform", lambda y,sr,w,h,p: [(0.0, 0.5, y)], raising=True)
    monkeypatch.setattr(CL, "run_inference", lambda at, seg: (np.array([0.2,0.1,0.6,0.1], dtype=np.float32), ["animal","vehicle","shotgun","other"]), raising=False)
    monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)

    a = tmp_path / "a.wav"; a.write_bytes(b"RIFF....WAVE")
    argv = ["classify.py", "--audio", str(a), "--checkpoint", str(tmp_path/"ckpt.bin"),
            "--device", "cpu", "--window-sec", "0.5", "--hop-sec", "1.0"]
    monkeypatch.setattr(CL.sys, "argv", argv, raising=False)

    with caplog.at_level(CL.logging.WARNING):
        CL.main()
    assert any("hop-sec > window-sec" in m for m in caplog.messages)

def test_cli_loads_head_and_uses_predict_proba(monkeypatch, tmp_path: Path, capsys):
    """
    Provide a real --head path; patch joblib.load (and CL.load if present) to return DummyHead
    whose predict_proba is invoked. Ensures head branch is covered.
    """
    from scripts import classify as CL

    # write a pseudo head file
    head_path = tmp_path / "head.joblib"
    head_path.write_bytes(b"head")

    # minimal stack patches
    def fake_ensure(p, checkpoint_url=None):
        Path(p or (tmp_path/"ckpt.bin")).write_bytes(b"stub")
        return str(p or (tmp_path/"ckpt.bin"))
    monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure, raising=True)
    monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}), raising=True)

    import numpy as np
    wav = np.zeros(16000, dtype=np.float32)
    monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)

    # IMPORTANT: accept keyword args window_sec/hop_sec/pad_last
    monkeypatch.setattr(
        CL, "segment_waveform",
        lambda y, sr, window_sec=None, hop_sec=None, pad_last=None: [(0.0, 0.5, y)],
        raising=True
    )
    monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)

    # head & joblib.load
    class DummyHead:
        def __init__(self): self.classes_ = np.array(["animal","vehicle","shotgun","other"])
        def predict_proba(self, X):
            X = np.asarray(X)
            return np.repeat([[0.6, 0.2, 0.1, 0.1]], X.shape[0], axis=0)

    # Patch the real joblib.load (since classify likely imported 'load' directly)
    import joblib
    monkeypatch.setattr(joblib, "load", lambda path: DummyHead(), raising=True)
    # If classify did 'from joblib import load', patch that symbol too:
    if hasattr(CL, "load"):
        monkeypatch.setattr(CL, "load", lambda path: DummyHead(), raising=True)

    # Prefer embedding path if your code uses it, else run_inference
    monkeypatch.setattr(
        CL, "run_inference_with_embedding",
        lambda at, seg: (np.array([0.2, 0.1, 0.6, 0.1], dtype=np.float32),
                         ["animal","vehicle","shotgun","other"],
                         np.arange(8, dtype=np.float32)),
        raising=False
    )

    a = tmp_path / "a.wav"
    a.write_bytes(b"RIFF....WAVE")
    argv = ["classify.py", "--audio", str(a), "--checkpoint", str(tmp_path/"ckpt.bin"),
            "--device", "cpu", "--head", str(head_path)]
    monkeypatch.setattr(CL.sys, "argv", argv, raising=False)

    CL.main()
    _ = capsys.readouterr()  # optional: inspect output if needed

def test_cli_write_db_flow_with_fake_db(monkeypatch, tmp_path: Path):
    """
    Cover the --write-db branch: emulate DB module and verify calls.
    We keep the head loaded, so we must return a 2048-dim embedding.
    """
    from scripts import classify as CL
    from types import SimpleNamespace
    import numpy as np
    from pathlib import Path

    # Make sure no accidental HEAD-env overrides behavior
    monkeypatch.delenv("HEAD", raising=False)
    monkeypatch.setenv("HEAD", "")

    # minimal stack for the base model
    def fake_ensure(p, checkpoint_url=None):
        Path(p or (tmp_path / "ckpt.bin")).write_bytes(b"stub")
        return str(p or (tmp_path / "ckpt.bin"))

    monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure, raising=True)
    monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s, *a, **k: None}), raising=True)

    wav = np.zeros(16000, dtype=np.float32)
    monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)

    # segment: single window
    monkeypatch.setattr(
        CL,
        "segment_waveform",
        lambda y, sr, window_sec=None, hop_sec=None, pad_last=None: [(0.0, 0.5, y)],
        raising=True,
    )

    # aggregator: mean
    monkeypatch.setattr(
        CL,
        "aggregate_matrix",
        lambda M, mode="mean": M.mean(axis=0).astype(np.float32),
        raising=True,
    )

    # Return embedding with 2048 features to match the head pipeline (StandardScaler expects 2048)
    def _fake_run_inference_with_embedding(at, seg):
        probs = np.array([0.2, 0.1, 0.6, 0.1], dtype=np.float32)
        labels = ["animal", "vehicle", "shotgun", "other"]
        emb = np.arange(2048, dtype=np.float32)  # 2048-dim embedding
        return probs, labels, emb

    monkeypatch.setattr(CL, "run_inference_with_embedding", _fake_run_inference_with_embedding, raising=True)
    # --------------------------------

    # fake DB module used inside classify
    calls = {"open_db": 0, "upsert_run": 0, "finish_run": 0, "upsert_file": [], "upsert_file_aggregate": []}

    def fake_open_db(db_url, schema="audio_cls"):
        calls["open_db"] += 1
        return SimpleNamespace(closed=False)

    def fake_upsert_run(conn, meta):
        calls["upsert_run"] += 1

    def fake_finish_run(conn, run_id):
        calls["finish_run"] += 1

    def fake_upsert_file(conn, path, duration_s, sample_rate, size_bytes=None):
        fid = 1
        calls["upsert_file"].append((path, fid))
        return fid

    def fake_upsert_file_aggregate(conn, row):
        calls["upsert_file_aggregate"].append(row)

    import core.db_io_pg as dbmod

    monkeypatch.setattr(dbmod, "open_db", fake_open_db, raising=True)
    monkeypatch.setattr(dbmod, "upsert_run", fake_upsert_run, raising=True)
    monkeypatch.setattr(dbmod, "finish_run", fake_finish_run, raising=True)
    monkeypatch.setattr(dbmod, "upsert_file", fake_upsert_file, raising=True)
    monkeypatch.setattr(dbmod, "upsert_file_aggregate", fake_upsert_file_aggregate, raising=True)

    a = tmp_path / "a.wav"
    a.write_bytes(b"RIFF....WAVE")
    argv = [
        "classify.py",
        "--audio",
        str(a),
        "--checkpoint",
        str(tmp_path / "ckpt.bin"),
        "--device",
        "cpu",
        "--write-db",
        "--db-url",
        "postgres://u:p@h/db",
        "--db-schema",
        "audio_cls",
    ]
    monkeypatch.setattr(CL.sys, "argv", argv, raising=False)

    CL.main()
    assert calls["open_db"] == 1
    assert calls["upsert_run"] >= 1
    assert calls["finish_run"] == 1
    assert len(calls["upsert_file"]) == 1
    assert len(calls["upsert_file_aggregate"]) == 1

def test_cli_log_level_and_file_smoke(monkeypatch, tmp_path: Path):
    """
    Hit logging branch: --log-level/--log-file should not crash and initialize logging.
    """
    from scripts import classify as CL
    import numpy as np

    def fake_ensure(p, checkpoint_url=None):
        Path(p or (tmp_path/"ckpt.bin")).write_bytes(b"stub")
        return str(p or (tmp_path/"ckpt.bin"))
    monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure, raising=True)
    monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}), raising=True)

    wav = np.zeros(16000, dtype=np.float32)
    monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
    monkeypatch.setattr(CL, "segment_waveform", lambda y,sr,w,h,p: [(0.0, 0.5, y)], raising=True)
    monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)
    monkeypatch.setattr(CL, "run_inference", lambda at, seg: (np.array([0.2,0.1,0.6,0.1], dtype=np.float32), ["animal","vehicle","shotgun","other"]), raising=False)

    a = tmp_path / "a.wav"; a.write_bytes(b"RIFF....WAVE")
    logf = tmp_path / "log.txt"
    argv = ["classify.py", "--audio", str(a), "--checkpoint", str(tmp_path/"ckpt.bin"),
            "--device", "cpu", "--log-level", "INFO", "--log-file", str(logf)]
    monkeypatch.setattr(CL.sys, "argv", argv, raising=False)

    CL.main()
    assert logf.exists() and logf.stat().st_size >= 0
