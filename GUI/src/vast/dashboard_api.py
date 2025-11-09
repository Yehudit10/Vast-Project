# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import time
import pathlib
from typing import Dict, List, Optional, Tuple, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---- Optional deps (don't crash if missing) ----
try:
    from minio import Minio
    from minio.error import S3Error
except Exception:
    Minio = None  # type: ignore
    S3Error = Exception  # type: ignore

try:
    from vast.rel_db import RelDB
except Exception:
    RelDB = None  # type: ignore


# =========================
#        CONFIG
# =========================
# --- HTTP API ---
DB_API_BASE = os.getenv("DB_API_BASE", "http://host.docker.internal:8001")
DB_API_AUTH_MODE = os.getenv("DB_API_AUTH_MODE", "service")  # "service" | "bearer"
DB_API_TOKEN_FILE = os.getenv("DB_API_TOKEN_FILE", "/app/secrets/db_api_token")
DB_API_TOKEN = os.getenv("DB_API_TOKEN", "auto")
DB_API_SERVICE_NAME = os.getenv("DB_API_SERVICE_NAME", "GUI_H")

# --- RelDB (used inside RelDB class; here only for reference/env) ---
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "missions_user")
DB_PASS = os.getenv("DB_PASS", "pg123")
DB_NAME = os.getenv("DB_NAME", "missions_db")

# --- MinIO ---
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9001")  # host:exposed_port
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

DEFAULT_GROUND_BUCKET = os.getenv("GROUND_BUCKET", "ground")
DEFAULT_GROUND_PREFIX = os.getenv("GROUND_PREFIX", "")


# =========================
#   TOKEN BOOTSTRAP HELPERS
# =========================
def _safe_join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"

def _read_token_from_file(path: str) -> Optional[str]:
    p = pathlib.Path(path)
    if p.exists():
        token = p.read_text(encoding="utf-8").strip()
        return token or None
    return None

def _fetch_token_via_dev_bootstrap(base: str, retries: int = 3, backoff: float = 0.8) -> Optional[str]:
    """
    Calls /auth/_dev_bootstrap to mint/rotate a service token for this GUI.
    """
    url = _safe_join_url(base, "/auth/_dev_bootstrap")
    payload = {"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": True}
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code in (200, 201):
                data = r.json()
                raw = (data.get("service_account", {}) or {}).get("raw_token") \
                      or (data.get("service_account", {}) or {}).get("token")
                if raw and isinstance(raw, str) and "***" not in raw:
                    return raw.strip()
        except Exception as e:
            last_exc = e
        time.sleep(backoff * attempt)
    if last_exc:
        print(f"[BOOTSTRAP][WARN] last error: {last_exc}")
    return None

def get_or_bootstrap_token() -> Optional[str]:
    print(f"[DEBUG] Checking for existing token file at: {DB_API_TOKEN_FILE}", flush=True)

    if DB_API_TOKEN and DB_API_TOKEN.lower() != "auto":
        print(f"[DEBUG] Using static token from config", flush=True)
        return DB_API_TOKEN

    token = _read_token_from_file(DB_API_TOKEN_FILE)
    if token:
        print(f"[DEBUG] Loaded token from {DB_API_TOKEN_FILE}", flush=True)
        return token

    print(f"[DEBUG] No token found, bootstrapping via {DB_API_BASE}/auth/_dev_bootstrap", flush=True)
    token = _fetch_token_via_dev_bootstrap(DB_API_BASE)
    if token:
        p = pathlib.Path(DB_API_TOKEN_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(token, encoding="utf-8")
        print(f"[BOOTSTRAP] wrote token to {DB_API_TOKEN_FILE}", flush=True)
        return token

    print("[BOOTSTRAP][ERROR] Failed to obtain token.", flush=True)
    return None


# =========================
#        UTILITIES
# =========================
def _image_id_from_object_key(object_key: str) -> str:
    """
    'some/prefix/image (3).jpg' -> 'image (3)'
    """
    base = os.path.basename(object_key or "")
    return base.rsplit(".", 1)[0] if "." in base else base


# =========================
#       DASHBOARD API
# =========================
class DashboardApi:
    """
    Unified client:
      - REST to DB-API (with token bootstrap)
      - Optional MinIO helper
      - Optional RelDB helper
    """

    def __init__(self) -> None:
        # ---- HTTP session ----
        self.base = DB_API_BASE.rstrip("/")
        self.http = requests.Session()
        token = get_or_bootstrap_token()
        if token:
            if DB_API_AUTH_MODE == "service":
                self.http.headers.update({"X-Service-Token": token})
            else:
                self.http.headers.update({"Authorization": f"Bearer {token}"})
        self.http.headers.update({"Content-Type": "application/json"})
        retry = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.http.mount("http://", HTTPAdapter(max_retries=retry))
        self.http.mount("https://", HTTPAdapter(max_retries=retry))

        # ---- MinIO (optional) ----
        self.minio = None
        if Minio is not None:
            try:
                self.minio = Minio(
                    MINIO_ENDPOINT,
                    access_key=MINIO_ACCESS_KEY,
                    secret_key=MINIO_SECRET_KEY,
                    secure=MINIO_SECURE,
                )
            except Exception as e:
                print(f"[MINIO][INIT][WARN] {e}")

        # ---- RelDB (optional) ----
        self.rdb = None
        if RelDB is not None:
            try:
                self.rdb = RelDB()
            except Exception as e:
                print(f"[RelDB][INIT][WARN] {e}")

    # ---------------------------
    # REST: examples / utilities
    # ---------------------------
    def list_devices(self, model: Optional[str] = None) -> List[dict]:
        url = f"{self.base}/api/devices"
        if model:
            url += f"?model={model}"
        try:
            r = self.http.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
            print(f"[API ERROR] {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"[API FAIL] {e}")
        return []

    def bulk_set_task_thresholds_labeled(
        self,
        mapping: dict[tuple[str, str], float] | List[dict],
        updated_by: str = "gui",
    ) -> dict:
        """
        Unified + fallback:
          1) POST /api/task_thresholds/batch
          2) if 404/405 -> POST /api/thresholds/batch
        """
        items = ([
            {"task": t, "label": l or "", "threshold": thr, "updated_by": updated_by}
            for (t, l), thr in mapping.items()
        ] if isinstance(mapping, dict) else mapping)

        paths = ["/api/task_thresholds/batch", "/api/thresholds/batch"]
        last_err: Optional[str] = None
        for path in paths:
            url = f"{self.base}{path}"
            try:
                r = self.http.post(url, json=items, timeout=20)
                if r.status_code in (200, 201):
                    data = r.json()
                    return {"ok": list(data.get("ok", [])), "fail": list(data.get("fail", []))}
                if r.status_code in (404, 405):
                    # try next path
                    last_err = f"http-{r.status_code}"
                    continue
                # other HTTP error
                return {"ok": [], "fail": [[[i.get("task"), i.get("label","")], f"http-{r.status_code} {r.text[:200]}"] for i in items]}
            except Exception as e:
                last_err = str(e)
                continue
        return {"ok": [], "fail": [[[i.get("task"), i.get("label","")], last_err or "unknown"] for i in items]}

    # ---------------------------
    # MinIO helpers (optional)
    # ---------------------------
    def list_minio_objects(self, bucket: str, prefix: str = "", limit: int = 100) -> List[dict]:
        """
        Returns: [{'key': 'path/file.jpg', 'size': int, 'last_modified': iso}, ...]
        """
        if not self.minio:
            print("[MINIO][WARN] MinIO client not available")
            return []
        out: List[dict] = []
        try:
            for i, obj in enumerate(self.minio.list_objects(bucket, prefix=prefix, recursive=True)):
                if i >= limit:
                    break
                lm = getattr(obj, "last_modified", None)
                out.append({
                    "key": getattr(obj, "object_name", None) or getattr(obj, "name", None),
                    "size": getattr(obj, "size", None),
                    "last_modified": lm.isoformat() if lm else None,
                })
        except Exception as e:
            print(f"[MINIO LIST FAIL] {e}")
        return out

    def get_latest_minio_key(self, bucket: str, prefix: str = "") -> Optional[str]:
        objs = self.list_minio_objects(bucket, prefix=prefix, limit=200)
        if not objs:
            return None
        objs_sorted = sorted(objs, key=lambda o: o.get("last_modified") or "", reverse=True)
        key = objs_sorted[0].get("key")
        return key if isinstance(key, str) and key.strip() else None

    def get_image_bytes_from_minio(self, key: str, bucket: Optional[str] = None) -> Optional[bytes]:
        if not self.minio:
            print("[MINIO][WARN] MinIO client not available")
            return None
        bucket_name = bucket or DEFAULT_GROUND_BUCKET
        try:
            response = self.minio.get_object(bucket_name, key)
            data = response.read()
            response.close()
            response.release_conn()
            print(f"[DEBUG] Got {len(data)} bytes from {bucket_name}/{key}")
            return data
        except Exception as e:
            print(f"[MINIO GET FAIL] {e}")
        return None

    # ---------------------------
    # RelDB delegates (optional)
    # ---------------------------
    def _rdb_guard(self) -> bool:
        if not self.rdb:
            print("[RelDB][WARN] RelDB client not available")
            return False
        return True

    def get_weekly_phi(self) -> dict:
        if not self._rdb_guard(): return {}
        return self.rdb.get_weekly_phi()

    def get_latest_rows(self, limit: int = 20) -> List[dict]:
        if not self._rdb_guard(): return []
        return self.rdb.get_latest_anomalies(limit=limit)

    def get_latest_detections(self, limit: int = 20) -> List[dict]:
        if not self._rdb_guard(): return []
        return self.rdb.get_latest_anomalies(limit=limit)

    def get_rows_by_image(self, image_name: str, limit: int = 50) -> List[dict]:
        """
        image_name is image_id without extension.
        """
        if not self._rdb_guard(): return []
        return self.rdb.get_anomalies_by_image(image_name, limit=limit)

    def get_last_row_by_image(self, image_name: str) -> Optional[dict]:
        if not self._rdb_guard(): return None
        return self.rdb.get_last_anomaly_by_image(image_name)

    def get_rows_by_day(self, date_iso: str, limit: int = 1000) -> List[dict]:
        if not self._rdb_guard(): return []
        return self.rdb.get_anomalies_by_day(date_iso, limit=limit)

    # ---------------------------
    # Image-centric (MinIO→image_id→RelDB)
    # ---------------------------
    def get_latest_image_key(self) -> Optional[str]:
        """
        Prefer the newest in MinIO; if none—fallback to DB (if available).
        """
        key = None
        if self.minio:
            key = self.get_latest_minio_key(DEFAULT_GROUND_BUCKET, DEFAULT_GROUND_PREFIX)
            if key:
                return key
        if self.rdb:
            try:
                return self.rdb.get_latest_image_key()
            except Exception as e:
                print(f"[RelDB][WARN] get_latest_image_key fallback failed: {e}")
        return None

    def get_anomalies_for_image_key(self, object_key: str, limit: int = 50) -> List[dict]:
        if not self._rdb_guard(): return []
        image_id = _image_id_from_object_key(object_key)
        return self.rdb.get_anomalies_by_image(image_id, limit=limit)

    def get_anomalies_for_current_image(self, limit: int = 100) -> List[dict]:
        if not self._rdb_guard(): return []
        key = self.get_latest_image_key()
        if not key:
            return []
        image_id = _image_id_from_object_key(key)
        return self.rdb.get_anomalies_by_image(image_id, limit=limit)

    def get_last_anomaly_for_current_image(self) -> Optional[dict]:
        if not self._rdb_guard(): return None
        key = self.get_latest_image_key()
        if not key:
            return None
        image_id = _image_id_from_object_key(key)
        return self.rdb.get_last_anomaly_by_image(image_id)

    def get_phi_for_image(self, image_name_or_key: str) -> dict:
        if not self._rdb_guard(): return {"phi": None, "severity_avg": None, "density": None, "coverage": None, "trend": None}
        image_id = _image_id_from_object_key(image_name_or_key)
        return self.rdb.get_phi_for_image(image_id)

    def get_phi_for_current_image(self) -> dict:
        if not self._rdb_guard(): return {"phi": None, "severity_avg": None, "density": None, "coverage": None, "trend": None}
        key = self.get_latest_image_key()
        if not key:
            return {"phi": None, "severity_avg": None, "density": None, "coverage": None, "trend": None}
        image_id = _image_id_from_object_key(key)
        return self.rdb.get_phi_for_image(image_id)
