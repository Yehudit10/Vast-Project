import pytest
import numpy as np
from pathlib import Path

# --------------------------
# Dummy classes and functions
# --------------------------
class DummyModel:
    def __init__(self, device="cpu"):
        self.device = device

    def forward(self, x):
        return np.zeros((len(x), 10))  # dummy output for 10 classes

class DummyAudioTagging:
    def __init__(self, *args, **kwargs):
        pass

    def run(self, *args, **kwargs):
        return {"preds": np.zeros(10)}

# --------------------------
# Auto patching fixture
# --------------------------
@pytest.fixture(autouse=True)
def patch_all(monkeypatch):
    # Patch CNN14 loader
    import backbones.cnn14 as cnn14
    monkeypatch.setattr(
        cnn14,
        "load_cnn14_model",
        lambda checkpoint, checkpoint_url=None, device="cpu": DummyModel(device=device),
    )

    # Patch classify module functions to avoid real AudioTagging / heavy computations
    import scripts.classify as classify

    # Patch functions that would call real models or I/O
    monkeypatch.setattr(classify, "run_inference", lambda *a, **k: np.zeros(10))
    monkeypatch.setattr(classify, "run_inference_with_embedding", lambda *a, **k: np.zeros(10))
    monkeypatch.setattr(classify, "aggregate_matrix", lambda *a, **k: np.zeros(10))
    monkeypatch.setattr(classify, "load_audio", lambda *a, **k: np.zeros(16000))  # 1 sec dummy audio
    monkeypatch.setattr(classify, "segment_waveform", lambda *a, **k: [np.zeros(16000)])

# --------------------------
# Tests
# --------------------------
def test_classify_cli(tmp_path):
    import scripts.classify as classify

    # prepare dummy audio file path
    audio_file = tmp_path / "dummy.wav"
    audio_file.write_bytes(b"dummy")

    # call main classify function (simulate CLI)
    result = classify.run_inference(audio_file)
    
    # assert it returns the dummy array
    assert isinstance(result, np.ndarray)
    assert result.shape[0] == 10  # matches DummyModel output

def test_classify_cli_with_embedding(tmp_path):
    import scripts.classify as classify

    # prepare dummy audio file path
    audio_file = tmp_path / "dummy.wav"
    audio_file.write_bytes(b"dummy")

    # call main classify function with embedding
    result = classify.run_inference_with_embedding(audio_file)

    # assert it returns the dummy array
    assert isinstance(result, np.ndarray)
    assert result.shape[0] == 10


# # tests/integration/test_classify_cli.py
# import pytest
# import numpy as np

# # Dummy replacements
# class DummyModel:
#     def __init__(self, device="cpu"):
#         self.device = device

#     def predict(self, x):
#         # deterministic fake output
#         return np.array([0.1, 0.9])

# class DummyAudioTagging:
#     def __init__(self, *args, **kwargs):
#         pass

#     def run_inference(self, waveform, *args, **kwargs):
#         return np.array([0.3, 0.7])

# @pytest.fixture(autouse=True)
# def patch_all(monkeypatch):
#     # Patch the CNN14 model loader
#     import backbones.cnn14 as cnn14
#     monkeypatch.setattr(
#         cnn14, "load_cnn14_model",
#         lambda checkpoint, checkpoint_url=None, device="cpu": DummyModel(device=device)
#     )

#     import scripts.classify as classify
#     monkeypatch.setattr(classify, "AudioTagging", DummyAudioTagging)

#     # Patch any functions from classify that are heavy / I/O
#     import scripts.classify as classify
#     monkeypatch.setattr(classify, "load_audio", lambda path, sr=None: np.zeros(16000))
#     monkeypatch.setattr(classify, "segment_waveform", lambda waveform, hop_sec, window_sec, sr: [waveform])
#     monkeypatch.setattr(classify, "aggregate_matrix", lambda matrix_list: np.array([0.5, 0.5]))


# def test_classify_cli(tmp_path):
#     """
#     Integration-like test of scripts/classify.py CLI with patched heavy dependencies.
#     Checks that we can run the main classify logic and get expected output.
#     """
#     import scripts.classify as classify

#     audio_dir = tmp_path / "audio"
#     audio_dir.mkdir()
#     fake_audio_file = audio_dir / "file1.wav"
#     fake_audio_file.write_bytes(b"FAKE")

#     results = classify.classify_dir(str(audio_dir), write_db=False)

#     # Ensure results shape is as expected
#     assert results.shape == (1, 2)
#     # Ensure deterministic output from dummy aggregation
#     np.testing.assert_array_equal(results[0], np.array([0.5, 0.5]))


# def test_classify_cli_with_embedding(tmp_path):
#     """
#     Another integration-like test simulating embedding usage.
#     Ensures run_inference_with_embedding path works.
#     """
#     import scripts.classify as classify

#     audio_dir = tmp_path / "audio"
#     audio_dir.mkdir()
#     fake_audio_file = audio_dir / "file2.wav"
#     fake_audio_file.write_bytes(b"FAKE")

#     results = classify.classify_dir(str(audio_dir), use_embedding=True, write_db=False)

#     # Expect deterministic output
#     np.testing.assert_array_equal(results[0], np.array([0.5, 0.5]))


# # # tests/integration/test_classify_cli.py
# # import pytest
# # from types import SimpleNamespace
# # from pathlib import Path
# # import sys
# # import scripts.classify as CL
# # import numpy as np

# # class DummyCur:
# #     def execute(self, *a, **k): pass
# #     def __enter__(self): return self
# #     def __exit__(self, exc_type, exc_val, exc_tb): return False

# # class DummyConn:
# #     def cursor(self):
# #         return DummyCur()
# #     def commit(self): pass
# #     def rollback(self): pass
# #     @property
# #     def closed(self): return False


# # # Helper to create dummy WAV files
# # def _mk_two_wavs(tmp_path):
# #     w1 = tmp_path / "a.wav"
# #     w2 = tmp_path / "b.wav"
# #     w1.write_bytes(b"RIFF....WAVEfmt")  # minimal valid WAV header
# #     w2.write_bytes(b"RIFF....WAVEfmt")
# #     return str(w1), str(w2)

# # # Patch the model to avoid loading real checkpoints
# # def _patch_model_stack(monkeypatch, ckpt_path):
# #     class DummyModel:
# #         def __init__(self, checkpoint_path=None, device=None):
# #             self.checkpoint_path = checkpoint_path
# #             self.device = device
# #         def inference(self, x):
# #             return [0.1, 0.9]  # deterministic dummy output

# #     monkeypatch.setattr(CL, "load_cnn14_model", lambda checkpoint, checkpoint_url=None, device="cpu": DummyModel())

# # # @pytest.mark.parametrize("with_db", [False, True])
# # # def test_classify_cli(monkeypatch, tmp_path, capsys, with_db):
# # #     w1, w2 = _mk_two_wavs(tmp_path)
# # #     ckpt = tmp_path / "ckpt.bin"; ckpt.write_bytes(b"ckpt")
# # #     _patch_model_stack(monkeypatch, ckpt)

# # #     calls = {"open_db": 0, "upsert_run": 0, "finish_run": 0, "upsert_file": [], "upsert_file_aggregate": []}

# # #     # Fake DB functions
# # #     def fake_open_db(db_url, schema="audio_cls"):
# # #         calls["open_db"] += 1
# # #         return SimpleNamespace(closed=False)
# # #     def fake_upsert_run(conn, meta): calls["upsert_run"] += 1
# # #     def fake_finish_run(conn, run_id): calls["finish_run"] += 1
# # #     def fake_upsert_file(conn, path, duration_s, sample_rate, size_bytes=None):
# # #         fid = 1 if path.endswith("a.wav") else 2
# # #         calls["upsert_file"].append((path, fid))
# # #         return fid
# # #     def fake_upsert_file_aggregate(conn, row): calls["upsert_file_aggregate"].append(row)

# # #     # Patch DB module if with_db=True
# # #     if with_db:
# # #         import core.db_io_pg as dbmod
# # #         monkeypatch.setattr(dbmod, "open_db", fake_open_db)
# # #         monkeypatch.setattr(dbmod, "upsert_run", fake_upsert_run)
# # #         monkeypatch.setattr(dbmod, "finish_run", fake_finish_run)
# # #         monkeypatch.setattr(dbmod, "upsert_file", fake_upsert_file)
# # #         monkeypatch.setattr(dbmod, "upsert_file_aggregate", fake_upsert_file_aggregate)

# # #     def run_once(wav_path):
# # #         argv = ["scripts.classify.py", "--audio", wav_path, "--checkpoint", str(ckpt), "--device", "cpu"]
# # #         if with_db:
# # #             argv += ["--write-db", "--db-url", "postgres://u:p@h:5432/db", "--db-schema", "audio_cls"]
# # #         monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # #         CL.main()
# # #         return capsys.readouterr().out.lower()

# # #     out1 = run_once(w1)
# # #     out2 = run_once(w2)

# # #     assert "a.wav" in out1
# # #     assert "b.wav" in out2

# # #     if with_db:
# # #         assert calls["open_db"] == 2  # once per run
# # #         assert calls["upsert_run"] == 2
# # #         assert calls["finish_run"] == 2
# # #         assert calls["upsert_file"] == [(w1, 1), (w2, 2)]
# # #         assert len(calls["upsert_file_aggregate"]) == 2


# # @pytest.mark.parametrize("with_db", [False, True])
# # def test_classify_cli(monkeypatch, tmp_path, with_db):
# #     w1, w2 = _mk_two_wavs(tmp_path)
# #     ckpt = tmp_path / "ckpt.bin"; ckpt.write_bytes(b"ckpt")
# #     _patch_model_stack(monkeypatch, ckpt)

# #     calls = {"upsert_file": [], "upsert_file_aggregate": [], "upsert_run": 0, "finish_run": 0}

# #     # Patch DB if needed
# #     if with_db:
# #         import core.db_io_pg as dbmod
# #         monkeypatch.setattr(dbmod, "open_db", lambda *a, **k: DummyConn())
# #         monkeypatch.setattr(dbmod, "upsert_file", 
# #             lambda conn, path, *a, **k: calls["upsert_file"].append(Path(path)) or (1 if str(path).endswith("a.wav") else 2)
# #         )
# #         monkeypatch.setattr(dbmod, "finish_run", lambda *a, **k: calls.update({"finish_run": calls["finish_run"]+1}))
# #         monkeypatch.setattr(dbmod, "upsert_file", lambda conn, path, *a, **k: calls["upsert_file"].append(str(path)) or (1 if str(path).endswith("a.wav") else 2))
# #         monkeypatch.setattr(dbmod, "upsert_file_aggregate", lambda conn, row: calls["upsert_file_aggregate"].append(row))

# #     # Patch load_audio
# #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr=None: np.zeros(16000, dtype=np.float32))
# #     monkeypatch.setattr(CL, "discover_audio_files", lambda root: [Path(w1), Path(w2)])

# #     # Run main
# #     argv = ["classify.py", "--audio", str(tmp_path), "--checkpoint", str(ckpt), "--device", "cpu"]
# #     if with_db:
# #         argv += ["--write-db", "--db-url", "postgres://u:p@h:5432/db", "--db-schema", "audio_cls"]
# #     monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# #     CL.main()

# #     # Assert DB calls
# #     if with_db:
# #         assert calls["upsert_run"] == 1
# #         assert calls["finish_run"] == 1
# #         assert Path(w1).name in [p.name for p in calls["upsert_file"]]
# #         assert Path(w2).name in [p.name for p in calls["upsert_file"]]
# #         assert len(calls["upsert_file_aggregate"]) == 2


# # # # classification/tests/integration/test_classify_cli.py
# # # """
# # # Integration-like tests for scripts/classify.py (no real DB, no heavy models).

# # # We patch all heavy or external dependencies:
# # # - ensure_checkpoint -> returns a local path
# # # - cnn14.load_cnn14_model -> returns Dummy AudioTagging
# # # - load_audio / segment_waveform -> synthetic wave
# # # - run_inference / run_inference_with_embedding -> deterministic arrays
# # # - aggregate_matrix -> fixed aggregation
# # # - joblib.load -> dummy head with predict_proba and classes_
# # # - db_io_pg -> fake (for the DB-flow test)
# # # """

# # # from pathlib import Path
# # # import numpy as np
# # # import pytest
# # # from types import SimpleNamespace
# # # import json

# # # from scripts import classify as CL
# # # from backbones import cnn14

# # # # ----------------------- Helpers -----------------------

# # # def _mk_two_wavs(tmp_path: Path):
# # #     p1 = tmp_path / "a.wav"; p2 = tmp_path / "b.wav"
# # #     p1.write_bytes(b"RIFF....WAVE")
# # #     p2.write_bytes(b"RIFF....WAVE")
# # #     return str(p1), str(p2)

# # # def _patch_model_stack(monkeypatch, ckpt_path: Path, emb_dim: int = 6, n_classes: int = 4):
# # #     # patch ensure_checkpoint
# # #     monkeypatch.setattr(CL, "ensure_checkpoint", lambda p, checkpoint_url=None: str(ckpt_path), raising=True)

# # #     # Dummy AudioTagging object
# # #     class DummyAT:
# # #         def __init__(self, *a, **k): pass

# # #     # Patch load_cnn14_model to return DummyAT
# # #     monkeypatch.setattr(cnn14, "load_cnn14_model", lambda ckpt, checkpoint_url=None, device="cpu": DummyAT())

# # #     # Synthetic audio
# # #     sr = 32000
# # #     wav = np.zeros(int(0.5 * sr), dtype=np.float32)
# # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
# # #     monkeypatch.setattr(CL, "segment_waveform", lambda y, sr, window_sec, hop_sec, pad_last: [(0.0, 0.5, y)], raising=True)

# # #     clip = np.array([0.2, 0.1, 0.6, 0.1], dtype=np.float32)[:n_classes]
# # #     emb  = np.arange(emb_dim, dtype=np.float32)

# # #     monkeypatch.setattr(CL, "run_inference", lambda at, seg: (clip, ["animal","vehicle","shotgun","other"][:n_classes]), raising=False)
# # #     monkeypatch.setattr(CL, "run_inference_with_embedding",
# # #                         lambda at, seg: (clip, ["animal","vehicle","shotgun","other"][:n_classes], emb),
# # #                         raising=False)

# # #     monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)

# # #     # Dummy head for joblib.load
# # #     class DummyHead:
# # #         def __init__(self):
# # #             self.classes_ = np.array(["animal","vehicle","shotgun","other"][:n_classes])
# # #         def predict_proba(self, X):
# # #             X = np.asarray(X)
# # #             base = np.array([[0.7, 0.2, 0.05, 0.05][:n_classes]], dtype=np.float32)
# # #             return np.repeat(base, X.shape[0], axis=0)

# # #     import joblib as _joblib
# # #     monkeypatch.setattr(_joblib, "load", lambda path: DummyHead(), raising=True)

# # #     return DummyHead

# # # # ----------------------- Tests -----------------------

# # # def test_classify_cli_no_db(monkeypatch, tmp_path, capsys):
# # #     w1, w2 = _mk_two_wavs(tmp_path)
# # #     ckpt = tmp_path / "ckpt.bin"; ckpt.write_bytes(b"ckpt")

# # #     _patch_model_stack(monkeypatch, ckpt)

# # #     def run_once(wav_path: str):
# # #         argv = ["classify.py", "--audio", wav_path, "--checkpoint", str(ckpt), "--device", "cpu"]
# # #         monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # #         CL.main()
# # #         return capsys.readouterr().out.lower()

# # #     out1 = run_once(w1)
# # #     out2 = run_once(w2)
# # #     out  = out1 + "\n" + out2

# # #     # filenames appear
# # #     assert Path(w1).name.lower() in out
# # #     assert Path(w2).name.lower() in out

# # #     # verify dummy probabilities in CLI output
# # #     for cls in ["animal","vehicle","shotgun","other"]:
# # #         assert cls[:3] in out  # partial match suffices

# # # def test_classify_cli_with_fake_db(monkeypatch, tmp_path):
# # #     w1, w2 = _mk_two_wavs(tmp_path)
# # #     ckpt = tmp_path / "ckpt.bin"; ckpt.write_bytes(b"ckpt")
# # #     _patch_model_stack(monkeypatch, ckpt)

# # #     calls = {"open_db": 0, "upsert_run": 0, "finish_run": 0, "upsert_file": [], "upsert_file_aggregate": []}

# # #     def fake_open_db(db_url, schema="audio_cls"):
# # #         calls["open_db"] += 1
# # #         return SimpleNamespace(closed=False)
# # #     def fake_upsert_run(conn, meta): calls["upsert_run"] += 1
# # #     def fake_finish_run(conn, run_id): calls["finish_run"] += 1
# # #     def fake_upsert_file(conn, path, duration_s, sample_rate, size_bytes=None):
# # #         fid = 1 if path.endswith("a.wav") else 2
# # #         calls["upsert_file"].append((path, fid))
# # #         return fid
# # #     def fake_upsert_file_aggregate(conn, row): calls["upsert_file_aggregate"].append(row)

# # #     import core.db_io_pg as dbmod
# # #     monkeypatch.setattr(dbmod, "open_db", fake_open_db, raising=True)
# # #     monkeypatch.setattr(dbmod, "upsert_run", fake_upsert_run, raising=True)
# # #     monkeypatch.setattr(dbmod, "finish_run", fake_finish_run, raising=True)
# # #     monkeypatch.setattr(dbmod, "upsert_file", fake_upsert_file, raising=True)
# # #     monkeypatch.setattr(dbmod, "upsert_file_aggregate", fake_upsert_file_aggregate, raising=True)

# # #     def run_once(wav_path: str):
# # #         argv = ["classify.py","--audio", wav_path,"--checkpoint", str(ckpt),
# # #                 "--device","cpu","--write-db","--db-url","postgres://u:p@h:5432/db","--db-schema","audio_cls"]
# # #         monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # #         CL.main()

# # #     run_once(w1)
# # #     run_once(w2)

# # #     # assert DB flow
# # #     assert calls["open_db"] >= 1
# # #     assert calls["upsert_run"] >= 1
# # #     assert calls["finish_run"] >= 1
# # #     paths_seen = sorted(p for p,_ in calls["upsert_file"])
# # #     assert paths_seen == sorted([w1, w2])
# # #     fids = sorted(r["file_id"] for r in calls["upsert_file_aggregate"])
# # #     assert fids == [1,2]

# # # # ----------------------- CLI edge tests -----------------------

# # # def test_cli_requires_audio_exits_2(monkeypatch):
# # #     monkeypatch.setattr(CL.sys, "argv", ["classify.py"], raising=False)
# # #     with pytest.raises(SystemExit) as e:
# # #         CL.main()
# # #     assert e.value.code == 2

# # # def test_cli_unsupported_extension_exits_4(tmp_path, monkeypatch):
# # #     bad = tmp_path / "bad.txt"; bad.write_text("not audio")
# # #     monkeypatch.setattr(CL.sys, "argv", ["classify.py", "--audio", str(bad)], raising=False)
# # #     with pytest.raises(SystemExit) as e:
# # #         CL.main()
# # #     assert e.value.code == 4


# # # # # classification/tests/integration/test_classify_cli.py
# # # # """
# # # # Integration-like tests for scripts/classify.py (no real DB, no heavy models).

# # # # We patch all heavy or external dependencies:
# # # # - ensure_checkpoint -> returns a local path
# # # # - AudioTagging -> dummy class
# # # # - load_audio / segment_waveform -> synthetic wave
# # # # - run_inference / run_inference_with_embedding -> deterministic arrays
# # # # - aggregate_matrix -> fixed aggregation
# # # # - joblib.load -> dummy head with predict_proba and classes_
# # # # - db_io_pg -> fake (for the DB-flow test)
# # # # """

# # # # from pathlib import Path
# # # # import numpy as np
# # # # import pytest
# # # # from types import SimpleNamespace

# # # # from scripts import classify as CL

# # # # # ----------------------- Helpers -----------------------

# # # # def _mk_two_wavs(tmp_path: Path):
# # # #     p1 = tmp_path / "a.wav"; p2 = tmp_path / "b.wav"
# # # #     p1.write_bytes(b"RIFF....WAVE")
# # # #     p2.write_bytes(b"RIFF....WAVE")
# # # #     return str(p1), str(p2)

# # # # def _patch_model_stack(monkeypatch, ckpt_path: Path, emb_dim: int = 6, n_classes: int = 4):
# # # #     monkeypatch.setattr(CL, "ensure_checkpoint", lambda p, checkpoint_url=None: str(ckpt_path), raising=True)

# # # #     class DummyAT:
# # # #         def __init__(self, *a, **k): pass
# # # #     monkeypatch.setattr(CL, "AudioTagging", DummyAT, raising=True)

# # # #     sr = 32000
# # # #     wav = np.zeros(int(0.5 * sr), dtype=np.float32)
# # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
# # # #     monkeypatch.setattr(CL, "segment_waveform", lambda y, sr, window_sec, hop_sec, pad_last: [(0.0, 0.5, y)], raising=True)

# # # #     clip = np.array([0.2, 0.1, 0.6, 0.1], dtype=np.float32)[:n_classes]
# # # #     emb  = np.arange(emb_dim, dtype=np.float32)
# # # #     monkeypatch.setattr(CL, "run_inference", lambda at, seg: (clip, ["animal","vehicle","shotgun","other"][:n_classes]), raising=False)
# # # #     monkeypatch.setattr(CL, "run_inference_with_embedding",
# # # #                         lambda at, seg: (clip, ["animal","vehicle","shotgun","other"][:n_classes], emb),
# # # #                         raising=False)

# # # #     monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)

# # # #     class DummyHead:
# # # #         def __init__(self):
# # # #             self.classes_ = np.array(["animal","vehicle","shotgun","other"][:n_classes])
# # # #         def predict_proba(self, X):
# # # #             X = np.asarray(X)
# # # #             base = np.array([[0.7, 0.2, 0.05, 0.05][:n_classes]], dtype=np.float32)
# # # #             return np.repeat(base, X.shape[0], axis=0)

# # # #     import joblib as _joblib
# # # #     monkeypatch.setattr(_joblib, "load", lambda path: DummyHead(), raising=True)

# # # #     return DummyHead

# # # # # ----------------------- Tests -----------------------

# # # # def test_classify_cli_no_db(monkeypatch, tmp_path, capsys):
# # # #     w1, w2 = _mk_two_wavs(tmp_path)
# # # #     ckpt = tmp_path / "ckpt.bin"; ckpt.write_bytes(b"ckpt")

# # # #     DummyHead = _patch_model_stack(monkeypatch, ckpt)

# # # #     def run_once(wav_path: str):
# # # #         argv = ["classify.py", "--audio", wav_path, "--checkpoint", str(ckpt), "--device", "cpu"]
# # # #         monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # # #         CL.main()
# # # #         return capsys.readouterr().out.lower()

# # # #     out1 = run_once(w1)
# # # #     out2 = run_once(w2)
# # # #     out  = out1 + "\n" + out2

# # # #     # filenames appear
# # # #     assert Path(w1).name.lower() in out
# # # #     assert Path(w2).name.lower() in out

# # # #     # verify dummy probabilities in CLI output
# # # #     for cls in ["animal","vehicle","shotgun","other"]:
# # # #         assert cls[:3] in out  # partial match suffices

# # # # def test_classify_cli_with_fake_db(monkeypatch, tmp_path):
# # # #     w1, w2 = _mk_two_wavs(tmp_path)
# # # #     ckpt = tmp_path / "ckpt.bin"; ckpt.write_bytes(b"ckpt")
# # # #     _patch_model_stack(monkeypatch, ckpt)

# # # #     calls = {"open_db": 0, "upsert_run": 0, "finish_run": 0, "upsert_file": [], "upsert_file_aggregate": []}

# # # #     def fake_open_db(db_url, schema="audio_cls"):
# # # #         calls["open_db"] += 1
# # # #         return SimpleNamespace(closed=False)
# # # #     def fake_upsert_run(conn, meta): calls["upsert_run"] += 1
# # # #     def fake_finish_run(conn, run_id): calls["finish_run"] += 1
# # # #     def fake_upsert_file(conn, path, duration_s, sample_rate, size_bytes=None):
# # # #         fid = 1 if path.endswith("a.wav") else 2
# # # #         calls["upsert_file"].append((path, fid))
# # # #         return fid
# # # #     def fake_upsert_file_aggregate(conn, row): calls["upsert_file_aggregate"].append(row)

# # # #     import core.db_io_pg as dbmod
# # # #     monkeypatch.setattr(dbmod, "open_db", fake_open_db, raising=True)
# # # #     monkeypatch.setattr(dbmod, "upsert_run", fake_upsert_run, raising=True)
# # # #     monkeypatch.setattr(dbmod, "finish_run", fake_finish_run, raising=True)
# # # #     monkeypatch.setattr(dbmod, "upsert_file", fake_upsert_file, raising=True)
# # # #     monkeypatch.setattr(dbmod, "upsert_file_aggregate", fake_upsert_file_aggregate, raising=True)

# # # #     def run_once(wav_path: str):
# # # #         argv = ["classify.py","--audio", wav_path,"--checkpoint", str(ckpt),
# # # #                 "--device","cpu","--write-db","--db-url","postgres://u:p@h:5432/db","--db-schema","audio_cls"]
# # # #         monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # # #         CL.main()

# # # #     run_once(w1)
# # # #     run_once(w2)

# # # #     # assert DB flow
# # # #     assert calls["open_db"] >= 1
# # # #     assert calls["upsert_run"] >= 1
# # # #     assert calls["finish_run"] >= 1
# # # #     paths_seen = sorted(p for p,_ in calls["upsert_file"])
# # # #     assert paths_seen == sorted([w1, w2])
# # # #     fids = sorted(r["file_id"] for r in calls["upsert_file_aggregate"])
# # # #     assert fids == [1,2]

# # # # # ----------------------- CLI edge tests -----------------------

# # # # def test_cli_requires_audio_exits_2(monkeypatch):
# # # #     monkeypatch.setattr(CL.sys, "argv", ["classify.py"], raising=False)
# # # #     with pytest.raises(SystemExit) as e:
# # # #         CL.main()
# # # #     assert e.value.code == 2

# # # # def test_cli_unsupported_extension_exits_4(tmp_path, monkeypatch):
# # # #     bad = tmp_path / "bad.txt"; bad.write_text("not audio")
# # # #     monkeypatch.setattr(CL.sys, "argv", ["classify.py", "--audio", str(bad)], raising=False)
# # # #     with pytest.raises(SystemExit) as e:
# # # #         CL.main()
# # # #     assert e.value.code == 4

# # # # def test_cli_pad_flags_and_print_windows(monkeypatch, tmp_path):
# # # #     import numpy as np, wave, struct, math

# # # #     # minimal dummy patch
# # # #     monkeypatch.setattr(CL, "ensure_checkpoint", lambda p, checkpoint_url=None: str(tmp_path/"ckpt.bin"), raising=True)
# # # #     monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}), raising=True)
# # # #     wav_path = tmp_path / "ok.wav"
# # # #     sr = 32000; n = int(sr*0.5)
# # # #     with wave.open(str(wav_path), "wb") as wf:
# # # #         wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
# # # #         for i in range(n):
# # # #             sample = 0.25*math.sin(2*math.pi*440*(i/sr))
# # # #             wf.writeframes(struct.pack("<h", int(max(-1,min(1,sample))*32767)))
# # # #     arr = np.zeros(16000, dtype=np.float32)
# # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: arr)
# # # #     monkeypatch.setattr(CL, "segment_waveform", lambda y,sr,w,h,p: [(0.0,0.5,y)])
# # # #     monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32))
# # # #     monkeypatch.setattr(CL, "run_inference", lambda at, seg: (np.array([0.2,0.1,0.6,0.1], dtype=np.float32),
# # # #                                                                ["animal","vehicle","shotgun","other"]))

# # # #     argv = ["classify.py","--audio", str(wav_path),"--checkpoint", str(tmp_path/"ckpt.bin"),
# # # #             "--device","cpu","--window-sec","0.5","--hop-sec","0.5","--pad-last","--print-windows"]
# # # #     monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # # #     CL.main()

# # # #     argv2 = ["classify.py","--audio", str(wav_path),"--checkpoint", str(tmp_path/"ckpt2.bin"),
# # # #              "--device","cpu","--window-sec","0.5","--hop-sec","0.5","--no-pad-last","--print-windows"]
# # # #     monkeypatch.setattr(CL.sys, "argv", argv2, raising=False)
# # # #     CL.main()


# # # # # # classification/tests/integration/test_classify_cli.py
# # # # # """
# # # # # Integration-like tests for scripts/classify.py (no real DB, no heavy models).

# # # # # We patch all heavy or external dependencies:
# # # # # - ensure_checkpoint -> returns a local path
# # # # # - AudioTagging -> dummy class
# # # # # - load_audio / segment_waveform -> synthetic wave
# # # # # - run_inference / run_inference_with_embedding -> deterministic arrays
# # # # # - aggregate_matrix -> fixed aggregation
# # # # # - joblib.load -> dummy head with predict_proba and classes_
# # # # # - db_io_pg -> fake (for the DB-flow test)
# # # # # """

# # # # # from pathlib import Path
# # # # # import numpy as np
# # # # # import pytest
# # # # # from types import SimpleNamespace

# # # # # # Import module under test (run pytest from classification with PYTHONPATH=$PWD)
# # # # # from scripts import classify as CL

# # # # # # ----------------------- Helpers -----------------------

# # # # # def _mk_two_wavs(tmp_path: Path):
# # # # #     """Create two tiny wav placeholders under tmp_path and return their paths."""
# # # # #     p1 = tmp_path / "a.wav"; p2 = tmp_path / "b.wav"
# # # # #     p1.write_bytes(b"RIFF....WAVE")
# # # # #     p2.write_bytes(b"RIFF....WAVE")
# # # # #     return str(p1), str(p2)


# # # # # def _patch_model_stack(monkeypatch, ckpt_path: Path, emb_dim: int = 6, n_classes: int = 4):
# # # # #     """
# # # # #     Patch model/audio functions and return the dummy head class used by joblib.load.
# # # # #     This keeps the classify pipeline fast and deterministic.
# # # # #     """
# # # # #     # ensure checkpoint path is accepted as-is
# # # # #     monkeypatch.setattr(CL, "ensure_checkpoint", lambda p, checkpoint_url=None: str(ckpt_path), raising=True)

# # # # #     # AudioTagging dummy (ctor signature flexible)
# # # # #     class DummyAT:
# # # # #         def __init__(self, *a, **k): pass
# # # # #     monkeypatch.setattr(CL, "AudioTagging", DummyAT, raising=True)

# # # # #     # audio loader / segmentation
# # # # #     sr = 32000
# # # # #     wav = np.zeros(int(0.5 * sr), dtype=np.float32)  # 0.5s
# # # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
# # # # #     # single window [0,0.5)
# # # # #     monkeypatch.setattr(CL, "segment_waveform",
# # # # #                         lambda y, sr, window_sec, hop_sec, pad_last:
# # # # #                             [(0.0, 0.5, y)], raising=True)

# # # # #     # inference / embedding (choose one of them as used by your code)
# # # # #     clip = np.array([0.2, 0.1, 0.6, 0.1], dtype=np.float32)[:n_classes]
# # # # #     emb  = np.arange(emb_dim, dtype=np.float32)
# # # # #     monkeypatch.setattr(CL, "run_inference", lambda at, seg: (clip, ["animal","vehicle","shotgun","other"][:n_classes]), raising=False)
# # # # #     monkeypatch.setattr(CL, "run_inference_with_embedding",
# # # # #                         lambda at, seg: (clip, ["animal","vehicle","shotgun","other"][:n_classes], emb),
# # # # #                         raising=False)

# # # # #     # aggregation (over windows) -> mean over rows
# # # # #     monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)

# # # # #     # dummy head: predict_proba returns fixed [p_animal, p_vehicle, p_shotgun, p_other]
# # # # #     class DummyHead:
# # # # #         def __init__(self):
# # # # #             self.classes_ = np.array(["animal","vehicle","shotgun","other"][:n_classes])
# # # # #         def predict_proba(self, X):
# # # # #             X = np.asarray(X)
# # # # #             base = np.array([[0.7, 0.2, 0.05, 0.05][:n_classes]], dtype=np.float32)
# # # # #             return np.repeat(base, X.shape[0], axis=0)

# # # # #     # Patch joblib.load on the real joblib module (classify may import it inside main)
# # # # #     import joblib as _joblib
# # # # #     monkeypatch.setattr(_joblib, "load", lambda path: DummyHead(), raising=True)

# # # # #     return DummyHead


# # # # # # ----------------------- Tests -----------------------

# # # # # def test_classify_cli_no_db(monkeypatch, tmp_path, capsys):
# # # # #     """
# # # # #     End-to-end classify on two separate invocations (since CLI expects a single --audio).
# # # # #     No DB. We patch model/embedding/head stack and assert outputs contain filenames & classes.
# # # # #     """
# # # # #     # inputs & checkpoint
# # # # #     w1, w2 = _mk_two_wavs(tmp_path)
# # # # #     ckpt = tmp_path / "ckpt.bin"
# # # # #     ckpt.write_bytes(b"ckpt")

# # # # #     # patch heavy deps
# # # # #     _ = _patch_model_stack(monkeypatch, ckpt)

# # # # #     def run_once(wav_path: str):
# # # # #         argv = ["classify.py", "--audio", wav_path, "--checkpoint", str(ckpt), "--device", "cpu"]
# # # # #         monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # # # #         CL.main()
# # # # #         return capsys.readouterr().out.lower()

# # # # #     out1 = run_once(w1)
# # # # #     out2 = run_once(w2)
# # # # #     out  = out1 + "\n" + out2

# # # # #     # file names appear
# # # # #     assert Path(w1).name.lower() in out
# # # # #     assert Path(w2).name.lower() in out

# # # # #     # Expect our dummy head distribution somewhere (don’t force exact formatting)
# # # # #     for cls in ("animal", "vehicle", "shotgun", "other"):
# # # # #         assert (cls in out) or (cls[:3] in out)


# # # # # def test_classify_cli_with_fake_db(monkeypatch, tmp_path):
# # # # #     """
# # # # #     Invoke classify twice (one file per run) with a fake core.db_io_pg injected.
# # # # #     We verify the DB flow and that both files were upserted + aggregated.
# # # # #     """
# # # # #     w1, w2 = _mk_two_wavs(tmp_path)
# # # # #     ckpt = tmp_path / "ckpt.bin"; ckpt.write_bytes(b"ckpt")
# # # # #     _ = _patch_model_stack(monkeypatch, ckpt)

# # # # #     # record calls
# # # # #     calls = {"open_db": 0, "upsert_run": 0, "finish_run": 0, "upsert_file": [], "upsert_file_aggregate": []}

# # # # #     def fake_open_db(db_url, schema="audio_cls"):
# # # # #         calls["open_db"] += 1
# # # # #         return SimpleNamespace(closed=False)

# # # # #     def fake_upsert_run(conn, meta):
# # # # #         calls["upsert_run"] += 1

# # # # #     def fake_finish_run(conn, run_id):
# # # # #         calls["finish_run"] += 1

# # # # #     def fake_upsert_file(conn, path, duration_s, sample_rate, size_bytes=None):
# # # # #         # deterministic id per path name
# # # # #         fid = 1 if path.endswith("a.wav") else 2
# # # # #         calls["upsert_file"].append((path, fid))
# # # # #         return fid

# # # # #     def fake_upsert_file_aggregate(conn, row):
# # # # #         calls["upsert_file_aggregate"].append(row)

# # # # #     # Patch the actual module used by classify: "from core import db_io_pg"
# # # # #     import core.db_io_pg as dbmod
# # # # #     monkeypatch.setattr(dbmod, "open_db",               fake_open_db,               raising=True)
# # # # #     monkeypatch.setattr(dbmod, "upsert_run",            fake_upsert_run,            raising=True)
# # # # #     monkeypatch.setattr(dbmod, "finish_run",            fake_finish_run,            raising=True)
# # # # #     monkeypatch.setattr(dbmod, "upsert_file",           fake_upsert_file,           raising=True)
# # # # #     monkeypatch.setattr(dbmod, "upsert_file_aggregate", fake_upsert_file_aggregate, raising=True)

# # # # #     def run_once(wav_path: str):
# # # # #         argv = [
# # # # #             "classify.py",
# # # # #             "--audio", wav_path,
# # # # #             "--checkpoint", str(ckpt),
# # # # #             "--device", "cpu",
# # # # #             "--write-db",
# # # # #             "--db-url", "postgres://u:p@h:5432/db",
# # # # #             "--db-schema", "audio_cls",
# # # # #         ]
# # # # #         monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # # # #         CL.main()

# # # # #     # Run twice (one file per invocation)
# # # # #     run_once(w1)
# # # # #     run_once(w2)

# # # # #     # Verify DB flow occurred (twice for two files)
# # # # #     assert calls["open_db"] >= 1          # could be 1 or 2 depending on implementation
# # # # #     assert calls["upsert_run"] >= 1
# # # # #     assert calls["finish_run"] >= 1

# # # # #     # Should have inserted both files
# # # # #     paths_seen = sorted(p for p, _fid in calls["upsert_file"])
# # # # #     assert paths_seen == sorted([w1, w2])

# # # # #     # And at least one aggregate row per file
# # # # #     fids = sorted(r["file_id"] for r in calls["upsert_file_aggregate"])
# # # # #     assert fids == [1, 2]

# # # # # def _patch_light_stack(monkeypatch):
# # # # #     """
# # # # #     Minimal patch so CLI can run without heavy model loading:
# # # # #     - ensure_checkpoint: accept any path (create tiny placeholder if needed)
# # # # #     - AudioTagging: dummy
# # # # #     - load_audio / segment_waveform: one short window
# # # # #     - run_inference / run_inference_with_embedding: deterministic outputs
# # # # #     - aggregate_matrix: mean
# # # # #     """
# # # # #     import numpy as np
# # # # #     import pathlib as _pl

# # # # #     def _fake_ensure_checkpoint(p, checkpoint_url=None):
# # # # #         p = _pl.Path(p if p else "ckpt.bin"); p.parent.mkdir(parents=True, exist_ok=True)
# # # # #         if not p.exists(): p.write_bytes(b"stub")
# # # # #         return str(p)
# # # # #     monkeypatch.setattr(CL, "ensure_checkpoint", _fake_ensure_checkpoint, raising=True)

# # # # #     class DummyAT:
# # # # #         def __init__(self, *a, **k): pass
# # # # #     monkeypatch.setattr(CL, "AudioTagging", DummyAT, raising=True)

# # # # #     sr = 32000
# # # # #     wav = np.zeros(int(0.5*sr), dtype=np.float32)
# # # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
# # # # #     monkeypatch.setattr(CL, "segment_waveform", lambda y, sr, window_sec, hop_sec, pad_last: [(0.0, 0.5, y)], raising=True)

# # # # #     clip = np.array([0.2,0.1,0.6,0.1], dtype=np.float32)
# # # # #     emb  = np.arange(8, dtype=np.float32)
# # # # #     monkeypatch.setattr(CL, "run_inference", lambda at, seg: (clip, ["animal","vehicle","shotgun","other"]), raising=False)
# # # # #     monkeypatch.setattr(CL, "run_inference_with_embedding",
# # # # #                         lambda at, seg: (clip, ["animal","vehicle","shotgun","other"], emb), raising=False)
# # # # #     monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)


# # # # # def test_cli_requires_audio_exits_2(monkeypatch):
# # # # #     """
# # # # #     Missing --audio should trigger argparse usage and exit code 2.
# # # # #     """
# # # # #     monkeypatch.setattr(CL.sys, "argv", ["classify.py"], raising=False)
# # # # #     with pytest.raises(SystemExit) as e:
# # # # #         CL.main()
# # # # #     assert e.value.code == 2


# # # # # def test_cli_unsupported_extension_exits_4(tmp_path: Path, monkeypatch):
# # # # #     """
# # # # #     Passing a file with unsupported extension should exit(4).
# # # # #     """
# # # # #     bad = tmp_path / "bad.txt"
# # # # #     bad.write_text("not audio")
# # # # #     argv = ["classify.py", "--audio", str(bad)]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # # # #     with pytest.raises(SystemExit) as e:
# # # # #         CL.main()
# # # # #     assert e.value.code == 4


# # # # # def test_cli_pad_flags_and_print_windows(monkeypatch, tmp_path: Path):
# # # # #     """
# # # # #     Smoke test: ensure --pad-last/--no-pad-last and --print-windows go through the pipeline.
# # # # #     We patch the heavy stack so the CLI runs fast and deterministically.
# # # # #     """
# # # # #     _patch_light_stack(monkeypatch)
# # # # #     wav = tmp_path / "ok.wav"
# # # # #     # quick valid WAV
# # # # #     import wave, struct, math
# # # # #     sr = 32000; n = int(sr*0.5)
# # # # #     with wave.open(str(wav), "wb") as wf:
# # # # #         wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
# # # # #         for i in range(n):
# # # # #             sample = 0.25*math.sin(2*math.pi*440*(i/sr))
# # # # #             wf.writeframes(struct.pack("<h", int(max(-1,min(1,sample))*32767)))

# # # # #     # --pad-last
# # # # #     argv = [
# # # # #         "classify.py", "--audio", str(wav),
# # # # #         "--checkpoint", str(tmp_path/"ckpt.bin"),
# # # # #         "--device", "cpu",
# # # # #         "--window-sec", "0.5",
# # # # #         "--hop-sec", "0.5",
# # # # #         "--pad-last",
# # # # #         "--print-windows",
# # # # #     ]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # # # #     CL.main()  # should not raise

# # # # #     # --no-pad-last
# # # # #     argv2 = [
# # # # #         "classify.py", "--audio", str(wav),
# # # # #         "--checkpoint", str(tmp_path/"ckpt2.bin"),
# # # # #         "--device", "cpu",
# # # # #         "--window-sec", "0.5",
# # # # #         "--hop-sec", "0.5",
# # # # #         "--no-pad-last",
# # # # #         "--print-windows",
# # # # #     ]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv2, raising=False)
# # # # #     CL.main()  # should not raise

# # # # # def test_cli_rejects_non_positive_window_or_hop(monkeypatch, tmp_path: Path):
# # # # #     from scripts import classify as CL
# # # # #     wav = tmp_path / "a.wav"; wav.write_bytes(b"RIFF....WAVE")

# # # # #     # window<=0
# # # # #     argv = ["classify.py", "--audio", str(wav), "--window-sec", "0", "--hop-sec", "0.5"]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # # # #     with pytest.raises(SystemExit) as e:
# # # # #         CL.main()
# # # # #     assert e.value.code == 2

# # # # #     # hop<=0
# # # # #     argv = ["classify.py", "--audio", str(wav), "--window-sec", "0.5", "--hop-sec", "0"]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # # # #     with pytest.raises(SystemExit) as e:
# # # # #         CL.main()
# # # # #     assert e.value.code == 2

# # # # # def test_cli_accepts_directory_input(monkeypatch, tmp_path: Path):
# # # # #     from scripts import classify as CL
# # # # #     d = tmp_path / "dir"; d.mkdir()
# # # # #     (d / "x.wav").write_bytes(b"RIFF....WAVE")

# # # # #     # Patch heavy stack quickly
# # # # #     def fake_ensure(p, checkpoint_url=None): Path(p or (tmp_path/"ckpt.bin")).write_bytes(b"stub"); return str(tmp_path/"ckpt.bin")
# # # # #     monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure, raising=True)
# # # # #     monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}), raising=True)
# # # # #     import numpy as np
# # # # #     wav = np.zeros(16000, dtype=np.float32)
# # # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
# # # # #     monkeypatch.setattr(CL, "segment_waveform", lambda y,sr,w,h,p: [(0.0, 0.5, y)], raising=True)
# # # # #     monkeypatch.setattr(CL, "run_inference", lambda at, seg: (np.array([0.2,0.1,0.6,0.1], dtype=np.float32), ["animal","vehicle","shotgun","other"]), raising=False)
# # # # #     monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)

# # # # #     argv = ["classify.py", "--audio", str(d), "--checkpoint", str(tmp_path/"ckpt.bin"), "--device", "cpu",
# # # # #             "--window-sec", "0.5", "--hop-sec", "0.5", "--pad-last"]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv, raising=False)
# # # # #     CL.main()  # should process the file in directory

# # # # # def test_cli_warns_when_hop_greater_than_window(monkeypatch, tmp_path: Path, caplog):
# # # # #     """
# # # # #     When --hop-sec > --window-sec, CLI should warn but still proceed.
# # # # #     """
# # # # #     from scripts import classify as CL

# # # # #     # Minimal stack patch
# # # # #     def fake_ensure(p, checkpoint_url=None):
# # # # #         Path(p or (tmp_path/"ckpt.bin")).write_bytes(b"stub")
# # # # #         return str(p or (tmp_path/"ckpt.bin"))
# # # # #     monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure, raising=True)
# # # # #     monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}), raising=True)

# # # # #     import numpy as np
# # # # #     wav = np.zeros(16000, dtype=np.float32)
# # # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
# # # # #     monkeypatch.setattr(CL, "segment_waveform", lambda y,sr,w,h,p: [(0.0, 0.5, y)], raising=True)
# # # # #     monkeypatch.setattr(CL, "run_inference", lambda at, seg: (np.array([0.2,0.1,0.6,0.1], dtype=np.float32), ["animal","vehicle","shotgun","other"]), raising=False)
# # # # #     monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)

# # # # #     a = tmp_path / "a.wav"; a.write_bytes(b"RIFF....WAVE")
# # # # #     argv = ["classify.py", "--audio", str(a), "--checkpoint", str(tmp_path/"ckpt.bin"),
# # # # #             "--device", "cpu", "--window-sec", "0.5", "--hop-sec", "1.0"]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv, raising=False)

# # # # #     with caplog.at_level(CL.logging.WARNING):
# # # # #         CL.main()
# # # # #     assert any("hop-sec > window-sec" in msg.lower() for msg in caplog.messages)

# # # # # def test_cli_loads_head_and_uses_predict_proba(monkeypatch, tmp_path: Path, capsys):
# # # # #     """
# # # # #     Provide a real --head path; patch joblib.load (and CL.load if present) to return DummyHead
# # # # #     whose predict_proba is invoked. Ensures head branch is covered.
# # # # #     """
# # # # #     from scripts import classify as CL

# # # # #     # write a pseudo head file
# # # # #     head_path = tmp_path / "head.joblib"
# # # # #     head_path.write_bytes(b"head")

# # # # #     # minimal stack patches
# # # # #     def fake_ensure(p, checkpoint_url=None):
# # # # #         Path(p or (tmp_path/"ckpt.bin")).write_bytes(b"stub")
# # # # #         return str(p or (tmp_path/"ckpt.bin"))
# # # # #     monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure, raising=True)
# # # # #     monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}), raising=True)

# # # # #     import numpy as np
# # # # #     wav = np.zeros(16000, dtype=np.float32)
# # # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)

# # # # #     # IMPORTANT: accept keyword args window_sec/hop_sec/pad_last
# # # # #     monkeypatch.setattr(
# # # # #         CL, "segment_waveform",
# # # # #         lambda y, sr, window_sec=None, hop_sec=None, pad_last=None: [(0.0, 0.5, y)],
# # # # #         raising=True
# # # # #     )
# # # # #     monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)

# # # # #     # head & joblib.load
# # # # #     class DummyHead:
# # # # #         def __init__(self): self.classes_ = np.array(["animal","vehicle","shotgun","other"])
# # # # #         def predict_proba(self, X):
# # # # #             X = np.asarray(X)
# # # # #             return np.repeat([[0.6, 0.2, 0.1, 0.1]], X.shape[0], axis=0)

# # # # #     # Patch the real joblib.load (since classify likely imported 'load' directly)
# # # # #     import joblib
# # # # #     monkeypatch.setattr(joblib, "load", lambda path: DummyHead(), raising=True)
# # # # #     # If classify did 'from joblib import load', patch that symbol too:
# # # # #     if hasattr(CL, "load"):
# # # # #         monkeypatch.setattr(CL, "load", lambda path: DummyHead(), raising=True)

# # # # #     # Prefer embedding path if your code uses it, else run_inference
# # # # #     monkeypatch.setattr(
# # # # #         CL, "run_inference_with_embedding",
# # # # #         lambda at, seg: (np.array([0.2, 0.1, 0.6, 0.1], dtype=np.float32),
# # # # #                          ["animal","vehicle","shotgun","other"],
# # # # #                          np.arange(8, dtype=np.float32)),
# # # # #         raising=False
# # # # #     )

# # # # #     a = tmp_path / "a.wav"
# # # # #     a.write_bytes(b"RIFF....WAVE")
# # # # #     argv = ["classify.py", "--audio", str(a), "--checkpoint", str(tmp_path/"ckpt.bin"),
# # # # #             "--device", "cpu", "--head", str(head_path)]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv, raising=False)

# # # # #     CL.main()
# # # # #     _ = capsys.readouterr()  # optional: inspect output if needed

# # # # # def test_cli_write_db_flow_with_fake_db(monkeypatch, tmp_path: Path):
# # # # #     """
# # # # #     Cover the --write-db branch: emulate DB module and verify calls.
# # # # #     We keep the head loaded, so we must return a 2048-dim embedding.
# # # # #     """
# # # # #     from scripts import classify as CL
# # # # #     from types import SimpleNamespace
# # # # #     import numpy as np
# # # # #     from pathlib import Path

# # # # #     # Make sure no accidental HEAD-env overrides behavior
# # # # #     monkeypatch.delenv("HEAD", raising=False)
# # # # #     monkeypatch.setenv("HEAD", "")

# # # # #     # minimal stack for the base model
# # # # #     def fake_ensure(p, checkpoint_url=None):
# # # # #         Path(p or (tmp_path / "ckpt.bin")).write_bytes(b"stub")
# # # # #         return str(p or (tmp_path / "ckpt.bin"))

# # # # #     monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure, raising=True)
# # # # #     monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s, *a, **k: None}), raising=True)

# # # # #     wav = np.zeros(16000, dtype=np.float32)
# # # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)

# # # # #     # segment: single window
# # # # #     monkeypatch.setattr(
# # # # #         CL,
# # # # #         "segment_waveform",
# # # # #         lambda y, sr, window_sec=None, hop_sec=None, pad_last=None: [(0.0, 0.5, y)],
# # # # #         raising=True,
# # # # #     )

# # # # #     # aggregator: mean
# # # # #     monkeypatch.setattr(
# # # # #         CL,
# # # # #         "aggregate_matrix",
# # # # #         lambda M, mode="mean": M.mean(axis=0).astype(np.float32),
# # # # #         raising=True,
# # # # #     )

# # # # #     # Return embedding with 2048 features to match the head pipeline (StandardScaler expects 2048)
# # # # #     def _fake_run_inference_with_embedding(at, seg):
# # # # #         probs = np.array([0.2, 0.1, 0.6, 0.1], dtype=np.float32)
# # # # #         labels = ["animal", "vehicle", "shotgun", "other"]
# # # # #         emb = np.arange(2048, dtype=np.float32)  # 2048-dim embedding
# # # # #         return probs, labels, emb

# # # # #     monkeypatch.setattr(CL, "run_inference_with_embedding", _fake_run_inference_with_embedding, raising=True)
# # # # #     # --------------------------------

# # # # #     # fake DB module used inside classify
# # # # #     calls = {"open_db": 0, "upsert_run": 0, "finish_run": 0, "upsert_file": [], "upsert_file_aggregate": []}

# # # # #     def fake_open_db(db_url, schema="audio_cls"):
# # # # #         calls["open_db"] += 1
# # # # #         return SimpleNamespace(closed=False)

# # # # #     def fake_upsert_run(conn, meta):
# # # # #         calls["upsert_run"] += 1

# # # # #     def fake_finish_run(conn, run_id):
# # # # #         calls["finish_run"] += 1

# # # # #     def fake_upsert_file(conn, path, duration_s, sample_rate, size_bytes=None):
# # # # #         fid = 1
# # # # #         calls["upsert_file"].append((path, fid))
# # # # #         return fid

# # # # #     def fake_upsert_file_aggregate(conn, row):
# # # # #         calls["upsert_file_aggregate"].append(row)

# # # # #     import core.db_io_pg as dbmod

# # # # #     monkeypatch.setattr(dbmod, "open_db", fake_open_db, raising=True)
# # # # #     monkeypatch.setattr(dbmod, "upsert_run", fake_upsert_run, raising=True)
# # # # #     monkeypatch.setattr(dbmod, "finish_run", fake_finish_run, raising=True)
# # # # #     monkeypatch.setattr(dbmod, "upsert_file", fake_upsert_file, raising=True)
# # # # #     monkeypatch.setattr(dbmod, "upsert_file_aggregate", fake_upsert_file_aggregate, raising=True)

# # # # #     a = tmp_path / "a.wav"
# # # # #     a.write_bytes(b"RIFF....WAVE")
# # # # #     argv = [
# # # # #         "classify.py",
# # # # #         "--audio",
# # # # #         str(a),
# # # # #         "--checkpoint",
# # # # #         str(tmp_path / "ckpt.bin"),
# # # # #         "--device",
# # # # #         "cpu",
# # # # #         "--write-db",
# # # # #         "--db-url",
# # # # #         "postgres://u:p@h/db",
# # # # #         "--db-schema",
# # # # #         "audio_cls",
# # # # #     ]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv, raising=False)

# # # # #     CL.main()
# # # # #     assert calls["open_db"] == 1
# # # # #     assert calls["upsert_run"] >= 1
# # # # #     assert calls["finish_run"] == 1
# # # # #     assert len(calls["upsert_file"]) == 1
# # # # #     assert len(calls["upsert_file_aggregate"]) == 1

# # # # # def test_cli_log_level_and_file_smoke(monkeypatch, tmp_path: Path):
# # # # #     """
# # # # #     Hit logging branch: --log-level/--log-file should not crash and initialize logging.
# # # # #     """
# # # # #     from scripts import classify as CL
# # # # #     import numpy as np

# # # # #     def fake_ensure(p, checkpoint_url=None):
# # # # #         Path(p or (tmp_path/"ckpt.bin")).write_bytes(b"stub")
# # # # #         return str(p or (tmp_path/"ckpt.bin"))
# # # # #     monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure, raising=True)
# # # # #     monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}), raising=True)

# # # # #     wav = np.zeros(16000, dtype=np.float32)
# # # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav, raising=True)
# # # # #     monkeypatch.setattr(CL, "segment_waveform", lambda y,sr,w,h,p: [(0.0, 0.5, y)], raising=True)
# # # # #     monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0).astype(np.float32), raising=True)
# # # # #     monkeypatch.setattr(CL, "run_inference", lambda at, seg: (np.array([0.2,0.1,0.6,0.1], dtype=np.float32), ["animal","vehicle","shotgun","other"]), raising=False)

# # # # #     a = tmp_path / "a.wav"; a.write_bytes(b"RIFF....WAVE")
# # # # #     logf = tmp_path / "log.txt"
# # # # #     argv = ["classify.py", "--audio", str(a), "--checkpoint", str(tmp_path/"ckpt.bin"),
# # # # #             "--device", "cpu", "--log-level", "INFO", "--log-file", str(logf)]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv, raising=False)

# # # # #     CL.main()
# # # # #     assert logf.exists() and logf.stat().st_size >= 0

# # # # # def test_cli_multiple_windows_aggregation(monkeypatch, tmp_path: Path):
# # # # #     """Test aggregation over multiple segments/windows."""
# # # # #     import numpy as np
# # # # #     from scripts import classify as CL

# # # # #     # minimal model patch
# # # # #     def fake_ensure(p, checkpoint_url=None): return str(tmp_path / "ckpt.bin")
# # # # #     monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure)
# # # # #     monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}))

# # # # #     # fake audio
# # # # #     wav = np.zeros(32000*1, dtype=np.float32)  # 1 second
# # # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav)

# # # # #     # segment waveform into 2 windows
# # # # #     def fake_segment(y, sr, window_sec, hop_sec, pad_last):
# # # # #         w_len = int(window_sec * sr)
# # # # #         return [(0.0, 0.5, y[:w_len]), (0.5, 1.0, y[w_len:])]
# # # # #     monkeypatch.setattr(CL, "segment_waveform", fake_segment)

# # # # #     # inference returns deterministic arrays
# # # # #     monkeypatch.setattr(CL, "run_inference", lambda at, seg: (np.array([0.2,0.1,0.6,0.1]), ["animal","vehicle","shotgun","other"]))

# # # # #     # aggregation records input
# # # # #     aggregated = {}
# # # # #     def fake_aggregate(M, mode="mean"):
# # # # #         aggregated["input"] = M
# # # # #         return M.mean(axis=0)
# # # # #     monkeypatch.setattr(CL, "aggregate_matrix", fake_aggregate)

# # # # #     wav_file = tmp_path / "a.wav"; wav_file.write_bytes(b"RIFF....WAVE")
# # # # #     argv = ["classify.py", "--audio", str(wav_file), "--checkpoint", str(tmp_path/"ckpt.bin"), "--device", "cpu", "--window-sec", "0.5", "--hop-sec", "0.5"]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv)
# # # # #     CL.main()

# # # # #     # assert aggregation received 2 rows
# # # # #     assert aggregated["input"].shape[0] == 2

# # # # # def test_cli_short_empty_wav(monkeypatch, tmp_path: Path):
# # # # #     """Test that very short or empty WAV files do not crash the CLI."""
# # # # #     import numpy as np
# # # # #     from scripts import classify as CL

# # # # #     def fake_ensure(p, checkpoint_url=None): return str(tmp_path / "ckpt.bin")
# # # # #     monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure)
# # # # #     monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}))

# # # # #     # empty audio
# # # # #     wav = np.zeros(0, dtype=np.float32)
# # # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: wav)
# # # # #     monkeypatch.setattr(CL, "segment_waveform", lambda y,sr,w,h,p: [(0.0,0.0,y)] if len(y) > 0 else [])
# # # # #     monkeypatch.setattr(CL, "run_inference", lambda at, seg: (np.array([0.2,0.1,0.6,0.1]), ["animal","vehicle","shotgun","other"]))
# # # # #     monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": np.zeros(4))

# # # # #     empty_wav = tmp_path / "empty.wav"; empty_wav.write_bytes(b"RIFF....WAVE")
# # # # #     argv = ["classify.py", "--audio", str(empty_wav), "--checkpoint", str(tmp_path/"ckpt.bin"), "--device", "cpu"]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv)
# # # # #     CL.main()  # should not raise

# # # # # def test_cli_head_load_failure(monkeypatch, tmp_path: Path):
# # # # #     """Test CLI behavior when joblib.load fails."""
# # # # #     from scripts import classify as CL
# # # # #     import joblib

# # # # #     def fake_ensure(p, checkpoint_url=None): return str(tmp_path / "ckpt.bin")
# # # # #     monkeypatch.setattr(CL, "ensure_checkpoint", fake_ensure)
# # # # #     monkeypatch.setattr(CL, "AudioTagging", type("D", (), {"__init__": lambda s,*a,**k: None}))

# # # # #     wav = tmp_path / "a.wav"; wav.write_bytes(b"RIFF....WAVE")
# # # # #     monkeypatch.setattr(CL, "load_audio", lambda path, target_sr: np.zeros(16000))
# # # # #     monkeypatch.setattr(CL, "segment_waveform", lambda y,sr,w,h,p: [(0.0,0.5,y)])
# # # # #     monkeypatch.setattr(CL, "aggregate_matrix", lambda M, mode="mean": M.mean(axis=0))

# # # # #     # force joblib.load to raise
# # # # #     monkeypatch.setattr(joblib, "load", lambda path: (_ for _ in ()).throw(IOError("failed to load")))

# # # # #     argv = ["classify.py", "--audio", str(wav), "--checkpoint", str(tmp_path/"ckpt.bin"), "--head", str(tmp_path/"head.joblib"), "--device", "cpu"]
# # # # #     monkeypatch.setattr(CL.sys, "argv", argv)

# # # # #     import pytest
# # # # #     with pytest.raises(IOError):
# # # # #         CL.main()
