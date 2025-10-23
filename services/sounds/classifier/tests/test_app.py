from fastapi.testclient import TestClient
import classification.app as app_mod

def test_health_ok():
    client = TestClient(app_mod.app)
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert data.get("ok") is True

def test_classify_endpoint_200(monkeypatch):
    client = TestClient(app_mod.app)
    import classification.scripts.classify as cls
    monkeypatch.setattr(cls, "run_classification_job", lambda **k: {"label": "car", "probs": {"car": 1.0}})
    r = client.post("/classify", json={"s3_bucket": "b", "s3_key": "k.wav"})
    assert r.status_code == 200
    assert r.json()["label"] == "car"

def test_classify_endpoint_422_when_body_invalid():
    client = TestClient(app_mod.app)
    # Missing 's3_key' → FastAPI validation error (422)
    r = client.post("/classify", json={"s3_bucket": "b"})
    assert r.status_code == 422
