import os

def _client(token, factory):
    headers = {}
    if token: headers["Authorization"] = f"Bearer {token}"
    return factory(), headers

def test_auth_required_on_api_prefix(client_factory, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "dev-token")
    client, _ = _client(None, client_factory)
    r = client.get("/api/files")
    assert r.status_code in (401, 403)

def test_auth_rejects_wrong_token(client_factory, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "dev-token")
    client, h = _client("wrong", client_factory)
    r = client.get("/api/files", headers=h)
    assert r.status_code == 401

def test_auth_accepts_correct_token_and_routes_work(client_factory, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "dev-token")
    client, h = _client("dev-token", client_factory)

    r = client.get("/api/files", headers=h)
    assert r.status_code == 200 and r.json() == []

    r = client.post("/api/files", headers=h, json={"bucket": "b", "object_key": "k"})
    assert r.status_code in (200, 201) and r.json()["status"] == "ok"

    r = client.put("/api/files/b/k", headers=h, json={"size_bytes": 1})
    assert r.status_code == 200 and r.json()["status"] == "ok"

    r = client.delete("/api/files/b/k", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "deleted"
