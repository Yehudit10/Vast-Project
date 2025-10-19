def test_healthz(client_raw):
    r = client_raw.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

def test_ready(client_raw):
    r = client_raw.get("/ready")
    assert r.status_code == 200
    assert r.json().get("ready") is True
