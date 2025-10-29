
import json
import time
import pathlib
from typing import Dict, List
import requests
from urllib.parse import quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------- CONFIG ----------
DB_API_BASE = "http://host.docker.internal:8001" 
DB_API_AUTH_MODE = "service"
DB_API_TOKEN_FILE = "/app/secrets/db_api_token"
DB_API_TOKEN = "auto"
DB_API_SERVICE_NAME = "GUI_H"


# ---------- TOKEN BOOTSTRAP ----------
def _safe_join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"

def _read_token_from_file(path: str) -> str | None:
    p = pathlib.Path(path)
    if p.exists():
        token = p.read_text(encoding="utf-8").strip()
        return token or None
    return None

def _fetch_token_via_dev_bootstrap(base: str, retries: int = 3, backoff: float = 0.8) -> str | None:
    url = _safe_join_url(base, "/auth/_dev_bootstrap")
    payload = {"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": True}
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code in (200, 201):
                data = r.json()
                raw = (data.get("service_account", {}) or {}).get("raw_token") \
                    or (data.get("service_account", {}) or {}).get("token")
                if raw and isinstance(raw, str) and "***" not in raw:
                    return raw.strip()
        except Exception:
            time.sleep(backoff * attempt)
    return None


def get_or_bootstrap_token() -> str | None:
    print(f"[DEBUG] Checking for existing token file at: {DB_API_TOKEN_FILE}", flush=True)

    if DB_API_TOKEN and DB_API_TOKEN.lower() != "auto":
        print(f"[DEBUG] Using static token from config", flush=True)
        return DB_API_TOKEN

    token = _read_token_from_file(DB_API_TOKEN_FILE)
    if token:
        print(f"[DEBUG] Loaded token from {DB_API_TOKEN_FILE}", flush=True)
        return token

    print(f"[DEBUG] No existing token found, bootstrapping via {DB_API_BASE}/auth/_dev_bootstrap", flush=True)
    token = _fetch_token_via_dev_bootstrap(DB_API_BASE)
    if token:
        pathlib.Path(DB_API_TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(DB_API_TOKEN_FILE).write_text(token, encoding="utf-8")
        print(f"[BOOTSTRAP] wrote token to {DB_API_TOKEN_FILE}", flush=True)
        return token

    print("[BOOTSTRAP][ERROR] Failed to obtain token.", flush=True)
    return None




# ---------- API CLIENT ----------
class DashboardApi:
    def __init__(self):
        self.base = DB_API_BASE.rstrip("/")
        self.http = requests.Session()
        token = get_or_bootstrap_token()
        if token:
            if DB_API_AUTH_MODE == "service":
                self.http.headers.update({"X-Service-Token": token})
            else:
                self.http.headers.update({"Authorization": f"Bearer {token}"})
        self.http.headers.update({"Content-Type": "application/json"})
        self.http.mount("http://",  HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])))
        self.http.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])))

    # ---------- METHODS ----------

    def list_devices(self, model: str | None = None) -> list[dict]:
        
        url = f"{self.base}/api/devices"
        if model:
            url += f"?model={model}"
        try:
            r = self.http.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
            print(f"[API ERROR] {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"[API FAIL] {e}")
        return []

    # ---------- THRESHOLDS ----------
    def bulk_set_task_thresholds_labeled(
        self,
        mapping: dict[tuple[str, str], float],
        updated_by: str = "gui",
    ) -> dict:
        """
        mapping: {("ripeness",""): 0.8, ("disease","rot"): 0.66, ...}
        
        """
        # 1)  cast to items:
        items: list[dict] = []
        for (task, label), thr in mapping.items():
            items.append({
                "task": str(task),
                "label": str(label or ""),
                "threshold": float(thr),
                "updated_by": updated_by,
            })

        path = "/api/task_thresholds/batch" 
        url = _safe_join_url(self.base, path)
        try:
            r = self.http.post(url, json=items, timeout=20)
            if r.status_code in (200, 201):
                #  {"ok":[["ripeness",""],["disease","rot"]], "fail":[[("task","label"), "reason"], ...]}
                return r.json()
            return {
                "ok": [],
                "fail": [((i.get("task"), i.get("label", "")), f"http-{r.status_code} {r.text[:200]}")
                         for i in items]
            }
        except Exception as e:
            return {
                "ok": [],
                "fail": [((i.get("task"), i.get("label", "")), str(e)) for i in items]
            }
