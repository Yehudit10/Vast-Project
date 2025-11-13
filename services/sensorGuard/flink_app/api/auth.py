import os
import pathlib
import requests
import time

# === CONFIG ===
DB_API_BASE = os.getenv("DB_API_BASE", "http://db_api_service:8001")
DB_API_TOKEN_FILE = os.getenv("DB_API_TOKEN_FILE", "/opt/app/secrets/db_api_token")
DB_API_SERVICE_NAME = os.getenv("DB_API_SERVICE_NAME", "flink_job_sensors")
ROTATE_IF_EXISTS = True  # Can be set to False if token rotation is not desired on restart

# === PATH HELPERS ===
def _safe_join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"

def _read_token_from_file(path: str) -> str | None:
    try:
        p = pathlib.Path(path)
        if p.exists():
            token = p.read_text(encoding="utf-8").strip()
            if token and len(token) > 10:
                return token
    except Exception:
        pass
    return None

def _write_token_to_file(path: str, token: str) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(token, encoding="utf-8")
    print(f"[AUTH] Token saved to {path}", flush=True)

# === FETCH LOGIC ===
def _fetch_token_via_bootstrap(base: str, retries: int = 3, backoff: float = 1.0) -> str | None:
    url = _safe_join_url(base, "/auth/_dev_bootstrap")
    payload = {"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": ROTATE_IF_EXISTS}

    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code not in (200, 201):
                print(f"[AUTH] Bootstrap failed ({r.status_code}): {r.text[:200]}", flush=True)
                time.sleep(backoff * attempt)
                continue

            data = r.json()
            raw = (data.get("service_account", {}) or {}).get("raw_token") \
                or (data.get("service_account", {}) or {}).get("token")

            if raw and isinstance(raw, str) and raw.strip() and "***" not in raw:
                print("[AUTH] Token fetched successfully", flush=True)
                return raw.strip()
        except Exception as e:
            print(f"[AUTH] Exception: {e}", flush=True)
            time.sleep(backoff * attempt)
    print("[AUTH] Failed to bootstrap service token", flush=True)
    return None

# === PUBLIC API ===
def get_access_token(base_url: str | None = None) -> str:
    """
    Loads token from file if exists, otherwise bootstraps new one via /auth/_dev_bootstrap.
    Returns a valid token string.
    """
    base = base_url or DB_API_BASE
    token = _read_token_from_file(DB_API_TOKEN_FILE)
    if token:
        return token

    new_token = _fetch_token_via_bootstrap(base)
    if new_token:
        _write_token_to_file(DB_API_TOKEN_FILE, new_token)
        return new_token
    raise RuntimeError("[AUTH] Could not obtain or save service token")
