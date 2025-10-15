import json
import os
from pathlib import Path
from urllib.parse import quote


def _read_spooled(kind: str):
    spool = Path(os.environ["DRY_RUN_SPOOL"])
    return sorted(spool.glob(f"*{kind}.json"))


def _updates_map(body: dict) -> dict:
 
    for key in ("fields", "updates", "set", "payload", "values", "data"):
        val = body.get(key)
        if isinstance(val, dict):
            return val

    return {k: v for k, v in body.items()
            if k not in {"bucket", "object_key", "action", "event", "timestamp", "ts", "op", "type", "table"}}

def test_files_upsert_spools(client_overridden_auth):
    payload = {
        "bucket": "imagery",
        "object_key": "cam-01/2025-09-14 16-00-56.png",
        "content_type": "image/png",
        "size_bytes": 12345,
        "device_id": "cam-01",
        "metadata": {"hello": "world"},
    }
    r = client_overridden_auth.post("/api/files", json=payload)
    assert r.status_code == 201, r.text
    assert r.json().get("status") == "ok"

    files = _read_spooled("files_upsert")
    assert files, "Expected spooled 'files_upsert'"
    body = json.loads(files[-1].read_text(encoding="utf-8"))

    assert body["bucket"] == payload["bucket"]
    assert body["object_key"] == payload["object_key"]
    assert body["size_bytes"] == payload["size_bytes"]


def test_files_update_spools(client_overridden_auth):
    bucket = "imagery"
    object_key = "spa ces/obj 1.png"
    url_key = quote(object_key, safe="")

    r = client_overridden_auth.put(
        f"/api/files/{bucket}/{url_key}",
        json={"device_id": "dev-9", "size_bytes": 77},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "ok"

    files = _read_spooled("files_update")
    assert files, "Expected spooled 'files_update'"
    body = json.loads(files[-1].read_text(encoding="utf-8"))

    assert body["bucket"] == bucket
    assert body["object_key"] == object_key

    updates = _updates_map(body)
    assert updates.get("device_id") == "dev-9"
    assert updates.get("size_bytes") == 77


def test_files_delete_spools_and_decodes_url(client_overridden_auth):
    bucket = "imagery"
    object_key = "with spaces/obj 2.png"
    url_key = quote(object_key, safe="")

    r = client_overridden_auth.delete(f"/api/files/{bucket}/{url_key}")
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "deleted"

    files = _read_spooled("files_delete")
    assert files, "Expected spooled 'files_delete'"
    body = json.loads(files[-1].read_text(encoding="utf-8"))

    assert body["bucket"] == bucket
    assert body["object_key"] == object_key



