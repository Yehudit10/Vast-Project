def test_files_list_router_unit(client_overridden_auth, monkeypatch):
    # Fake list_files to avoid DB
    captured = {}
    def fake_list_files(bucket, device_id, limit):
        captured.update(bucket=bucket, device_id=device_id, limit=limit)
        return [{"file_id":1,"bucket":bucket or "imagery","object_key":"a/b.png","device_id":device_id or "dev-1"}]
    import app.tables.files.repo as repo_mod
    monkeypatch.setattr(repo_mod, "list_files", fake_list_files, raising=True)

    from urllib.parse import quote
    bucket = "with spaces"
    device_id = "cam-99"
    resp = client_overridden_auth.get(f"/api/files?bucket={quote(bucket)}&device_id={device_id}&limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 1
    assert captured["bucket"] == bucket
    assert captured["device_id"] == device_id
    assert captured["limit"] == 2
