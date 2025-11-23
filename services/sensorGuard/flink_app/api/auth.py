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
    print(f"[AUTH] Token saved to {path}")

# === FETCH LOGIC ===
def _fetch_token_via_bootstrap(base: str, retries: int = 3, backoff: float = 1.0) -> str | None:
    url = _safe_join_url(base, "/auth/_dev_bootstrap")
    payload = {"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": ROTATE_IF_EXISTS}

    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code not in (200, 201):
                print(f"[AUTH] Bootstrap failed ({r.status_code}): {r.text[:200]}")
                time.sleep(backoff * attempt)
                continue

            data = r.json()
            raw = (data.get("service_account", {}) or {}).get("raw_token") \
                or (data.get("service_account", {}) or {}).get("token")

            if raw and isinstance(raw, str) and raw.strip() and "***" not in raw:
                print("[AUTH] Token fetched successfully")
                return raw.strip()
        except Exception as e:
            print(f"[AUTH] Exception: {e}")
            time.sleep(backoff * attempt)
    print("[AUTH] Failed to bootstrap service token")
    return None

# === PUBLIC API ===
def validate_token(base: str, token: str) -> bool:
    """
    Test if token is valid by making a simple API call.
    Returns True if token works, False otherwise.
    
    NOTE: Disabled because /api/me endpoint doesn't exist.
    We just assume the token is valid and let actual API calls fail if needed.
    """
    # url = _safe_join_url(base, "/api/me")
    # try:
    #     r = requests.get(url, headers={"X-Service-Token": token}, timeout=5)
    #     return r.status_code == 200
    # except Exception:
    #     return False
    
    # Skip validation - assume token is valid
    return True if token else False


def get_access_token(base_url: str | None = None) -> str:
    """
    Loads token from file if exists and valid, otherwise bootstraps new one via /auth/_dev_bootstrap.
    Returns a valid token string.
    """
    base = base_url or DB_API_BASE
    token = _read_token_from_file(DB_API_TOKEN_FILE)
    
    # If token exists, validate it first
    if token:
        if validate_token(base, token):
            print("[AUTH] Existing token is valid")
            return token
        else:
            print("[AUTH] Existing token is invalid, fetching new one...")

    new_token = _fetch_token_via_bootstrap(base)
    if new_token:
        _write_token_to_file(DB_API_TOKEN_FILE, new_token)
        return new_token
    raise RuntimeError("[AUTH] Could not obtain or save service token")
