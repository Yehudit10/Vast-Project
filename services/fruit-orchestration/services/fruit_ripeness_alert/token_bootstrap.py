import os, pathlib, time, requests

DB_API_BASE         = os.getenv("DB_API_BASE", "").strip()
DB_API_TOKEN_FILE   = os.getenv("DB_API_TOKEN_FILE", "/app/secret/db_api_token")
DB_API_SERVICE_NAME = os.getenv("DB_API_SERVICE_NAME", "fruit_ripeness_alert").strip() or "fruit_ripeness_alert"

def _safe_join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"

def _read_token(path: str) -> str | None:
    p = pathlib.Path(path)
    if p.exists():
        t = p.read_text(encoding="utf-8").strip()
        if t and "***" not in t:
            return t
    return None

def _write_token(path: str, token: str) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(token, encoding="utf-8")

def _try_dev_bootstrap():
    """Try to get token using /auth/_dev_bootstrap (new API)."""
    url = _safe_join_url(DB_API_BASE, "/auth/_dev_bootstrap")
    payload = {"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code in (200, 201):
            data = r.json()
            sa = data.get("service_account") or {}
            token = sa.get("raw_token") or sa.get("token")
            if token and "***" not in token:
                print("[BOOTSTRAP] obtained token via /auth/_dev_bootstrap")
                return token.strip()
        print(f"[BOOTSTRAP][WARN] _dev_bootstrap returned {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"[BOOTSTRAP][ERROR] {e}")
    return None

def get_service_token() -> str | None:
    """Get or create a service token automatically."""
    if not DB_API_BASE:
        print("[BOOTSTRAP][WARN] DB_API_BASE not set")
        return None

    # Try existing file
    token = _read_token(DB_API_TOKEN_FILE)
    if token:
        print(f"[BOOTSTRAP] using existing token from {DB_API_TOKEN_FILE}")
        return token

    # Try bootstrap (new unified API)
    print(f"[BOOTSTRAP] fetching new service token from {DB_API_BASE}")
    token = _try_dev_bootstrap()
    if token:
        _write_token(DB_API_TOKEN_FILE, token)
        print(f"[BOOTSTRAP] wrote token to {DB_API_TOKEN_FILE}")
        return token

    print("[BOOTSTRAP][ERROR] Could not obtain service token.")
    return None