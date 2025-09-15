# tests/integration/test_classify_finalize.py
from pathlib import Path
import numpy as np
from types import SimpleNamespace
import pytest

from scripts import classify as CL


def _patch_minimal_stack_for_exception(monkeypatch, tmp_path: Path):
    # Accept arbitrary checkpoint; create stub file
    def _fake_ensure(p, checkpoint_url=None):
        p = Path(p or tmp_path/"ckpt.bin"); p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists(): p.write_bytes(b"x")
        return str(p)
    monkeypatch.setattr(CL, "ensure_checkpoint", _fake_ensure, raising=True)

    class DummyAT: 
        def __init__(self, *a, **k): pass
    monkeypatch.setattr(CL, "AudioTagging", DummyAT, raising=True)

    # One short audio file
    wav = tmp_path / "a.wav"; wav.write_bytes(b"RIFF....WAVE")
    # Simple audio/segmentation and inference that raises once
    sr = 32000
    y = np.zeros(int(0.5*sr), dtype=np.float32)
    monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: y, raising=True)
    monkeypatch.setattr(CL, "segment_waveform", lambda *a, **k: [(0.0, 0.5, y)], raising=True)

    # First call raises to simulate failure in loop
    state = {"raised": False}
    def _run_inference_with_embedding(at, seg):
        if not state["raised"]:
            state["raised"] = True
            raise RuntimeError("simulated failure")
        return (np.array([0.1,0.2,0.3,0.4], dtype=np.float32), ["a","b","c","d"], np.arange(8, dtype=np.float32))
    monkeypatch.setattr(CL, "run_inference_with_embedding", _run_inference_with_embedding, raising=True)

    # Mean aggregator
    monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)


def test_finish_run_called_on_exception(monkeypatch, tmp_path: Path):
    _patch_minimal_stack_for_exception(monkeypatch, tmp_path)

    # Fake DB layer used by classify (module-level import)
    calls = {"finish_run": 0}
    class FakeDB:
        def open_db(url, schema="audio_cls"): return SimpleNamespace(closed=False)
        def upsert_run(conn, meta): pass
        def upsert_file(conn, path, duration_s, sample_rate, size_bytes=None): return 1
        def upsert_file_aggregate(conn, row): pass
        def finish_run(conn, run_id): calls["finish_run"] += 1

    # Patch core.db_io_pg used inside classify
    import core.db_io_pg as dbmod
    monkeypatch.setattr(dbmod, "open_db", FakeDB.open_db, raising=True)
    monkeypatch.setattr(dbmod, "upsert_run", FakeDB.upsert_run, raising=True)
    monkeypatch.setattr(dbmod, "upsert_file", FakeDB.upsert_file, raising=True)
    monkeypatch.setattr(dbmod, "upsert_file_aggregate", FakeDB.upsert_file_aggregate, raising=True)
    monkeypatch.setattr(dbmod, "finish_run", FakeDB.finish_run, raising=True)

    argv = [
        "classify.py",
        "--audio", str(tmp_path),
        "--checkpoint", str(tmp_path/"ckpt.bin"),
        "--device", "cpu",
        "--write-db", "--db-url", "postgres://x/y",
    ]
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    monkeypatch.setattr(CL.sys, "argv", argv, raising=False)

    # Should not propagate the exception; classify catches/logs inside the loop
    CL.main()
    assert calls["finish_run"] == 1
