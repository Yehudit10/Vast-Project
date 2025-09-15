def _client(factory):
    return factory()

def test_healthz_ok(client_factory_main):
    client = _client(client_factory_main)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

def test_ready_ok(client_factory_main):
    client = _client(client_factory_main)
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"ready": True}
