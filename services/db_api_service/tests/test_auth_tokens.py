def test_jwt_access_token_allows_me(client_raw, bootstrap_tokens):
    access = bootstrap_tokens["access_token"]
    r = client_raw.get("/api/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("type") == "user"
    assert "username" in j

def test_invalid_jwt_rejected(client_raw):
    r = client_raw.get("/api/me", headers={"Authorization": "Bearer not.a.valid.token"})
    assert r.status_code in (401, 403)

def test_service_token_allows_me(client_raw, bootstrap_tokens):
    raw = bootstrap_tokens["service_raw"]
    r = client_raw.get("/api/me", headers={"X-Service-Token": raw})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("type") == "service"
    assert isinstance(j.get("name"), str)

def test_wrong_service_token_rejected(client_raw):
    r = client_raw.get("/api/me", headers={"X-Service-Token": "totally-wrong"})
    assert r.status_code in (401, 403)

def test_no_auth_rejected(client_raw):
    r = client_raw.get("/api/me")
    assert r.status_code in (401, 403)
