# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import time
import base64
import pathlib
from typing import Dict, List, Optional, Tuple, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---- Optional deps (do not crash if missing) ----
try:
    from minio import Minio
    from minio.error import S3Error
except Exception:  # pragma: no cover
    Minio = None  # type: ignore
    S3Error = Exception  # type: ignore

try:
    from vast.rel_db import RelDB
except Exception:  # pragma: no cover
    RelDB = None  # type: ignore


# =========================
#        CONFIG
# =========================
# --- HTTP API ---
DB_API_BASE = os.getenv("DB_API_BASE", "http://db_api_service:8001")
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
    Calls /auth/_dev_bootstrap to mint/rotate a service token for this client.
    """
    url = _safe_join_url(base, "/auth/_dev_bootstrap")
    payload = {"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": True}
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code in (200, 201):
                data = r.json() if r.content else {}
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
    if DB_API_TOKEN and DB_API_TOKEN.lower() != "auto":
        print("[DEBUG] Using static token from DB_API_TOKEN", flush=True)
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
      - REST to DB-API (with token bootstrap/refresh)
      - Optional MinIO helper
      - Optional RelDB helper
    """

    def __init__(self) -> None:
        # ---- HTTP session ----
        self.base = DB_API_BASE.rstrip("/")
        self.http = requests.Session()

        # Attach robust retries
        retry = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=frozenset(["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"])
        )
        self.http.mount("http://", HTTPAdapter(max_retries=retry))
        self.http.mount("https://", HTTPAdapter(max_retries=retry))
        self.http.headers.update({"Content-Type": "application/json"})

        # ---- Auth ----
        token = get_or_bootstrap_token()
        self.token: Optional[str] = token
        self.token_type = "service" if DB_API_AUTH_MODE == "service" else "bearer"
        self._apply_auth_header(token)

        # ---- MinIO (optional) ----
        self.minio: Optional[Minio] = None
        if Minio is not None:
            try:
                self.minio = Minio(
                    MINIO_ENDPOINT,
                    access_key=MINIO_ACCESS_KEY,
                    secret_key=MINIO_SECRET_KEY,
                    secure=MINIO_SECURE,
                )
            except Exception as e:  # pragma: no cover
                print(f"[MINIO][INIT][WARN] {e}")

        # ---- RelDB (optional) ----
        self.rdb: Optional[RelDB] = None
        if RelDB is not None:
            try:
                self.rdb = RelDB()
            except Exception as e:  # pragma: no cover
                print(f"[RelDB][INIT][WARN] {e}")

    # ---------------------------
    # Auth helpers
    # ---------------------------
    def _apply_auth_header(self, token: Optional[str]) -> None:
        # Clean previous header variants
        for h in ["X-Service-Token", "Authorization"]:
            if h in self.http.headers:
                del self.http.headers[h]
        if token:
            if DB_API_AUTH_MODE == "service":
                self.http.headers.update({"X-Service-Token": token})
            else:
                self.http.headers.update({"Authorization": f"Bearer {token}"})

    def get_token_info(self) -> dict:
        """
        Tries to decode JWT payload. If not a JWT, returns basic info.
        """
        t = self.token
        if not t:
            return {"type": self.token_type, "status": "missing"}

        if "." in t:
            try:
                payload_b64 = t.split(".")[1]
                padded = payload_b64 + "=" * (-len(payload_b64) % 4)
                data = json.loads(base64.urlsafe_b64decode(padded))
                exp = data.get("exp")
                secs_left = exp - int(time.time()) if exp else None
                return {"type": "jwt", "exp": exp, "secs_left": secs_left, "payload": data}
            except Exception:
                pass
        return {"type": self.token_type, "token_length": len(t)}

    def refresh_token(self) -> bool:
        """
        Fetches a new service token via dev bootstrap and updates headers + file.
        """
        new_token = _fetch_token_via_dev_bootstrap(self.base)
        if new_token:
            try:
                pathlib.Path(DB_API_TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
                pathlib.Path(DB_API_TOKEN_FILE).write_text(new_token, encoding="utf-8")
            except Exception as e:
                print(f"[TOKEN][WARN] Could not persist new token: {e}")
            self.token = new_token
            self._apply_auth_header(new_token)
            print("[TOKEN] refreshed", flush=True)
            return True
        print("[TOKEN][ERROR] refresh failed", flush=True)
        return False

    # ---------------------------
    # REST: examples / utilities
    # ---------------------------
    def list_devices(self, model: Optional[str] = None) -> List[dict]:
        """
        Tries modern path /api/devices; falls back to /api/tables/devices for older servers.
        """
        paths = ["/api/devices", "/api/tables/devices"]
        last_err: Optional[str] = None
        for path in paths:
            url = f"{self.base}{path}"
            if model:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}model={model}"
            try:
                r = self.http.get(url, timeout=10)
                if r.status_code == 200:
                    try:
                        return r.json()
                    except Exception:
                        print("[API WARN] devices response is not JSON", flush=True)
                        return []
                if r.status_code in (404, 405):
                    last_err = f"http-{r.status_code}"
                    continue
                print(f"[API ERROR] {r.status_code}: {r.text[:200]}")
                return []
            except Exception as e:
                last_err = str(e)
                continue
        if last_err:
            print(f"[API FAIL] list_devices: {last_err}")
        return []

    def bulk_set_task_thresholds_labeled(
        self,
        mapping: Dict[Tuple[str, str], float] | List[dict],
        updated_by: str = "gui",
    ) -> dict:
        """
        Unified + fallback:
          1) POST /api/task_thresholds/batch
          2) if 404/405 -> POST /api/thresholds/batch
        Body shape is normalized to: {"task": str, "label": str, "threshold": float, "updated_by": str}
        """
        items = (
            [
                {"task": t, "label": l or "", "threshold": thr, "updated_by": updated_by}
                for (t, l), thr in mapping.items()
            ]
            if isinstance(mapping, dict) else mapping
        )

        paths = ["/api/task_thresholds/batch", "/api/thresholds/batch"]
        last_err: Optional[str] = None
        for path in paths:
            url = f"{self.base}{path}"
            try:
                r = self.http.post(url, json=items, timeout=20)
                if r.status_code in (200, 201):
                    data = r.json() if r.content else {}
                    return {"ok": list(data.get("ok", [])), "fail": list(data.get("fail", []))}
                if r.status_code in (404, 405):
                    last_err = f"http-{r.status_code}"
                    continue
                return {
                    "ok": [],
                    "fail": [[[i.get("task"), i.get("label","")], f"http-{r.status_code} {r.text[:200]}"] for i in items],
                }
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
        if not self._rdb_guard(): 
            return {"phi": None, "severity_avg": None, "density": None, "coverage": None, "trend": None}
        image_id = _image_id_from_object_key(image_name_or_key)
        return self.rdb.get_phi_for_image(image_id)

    def get_phi_for_current_image(self) -> dict:
        if not self._rdb_guard():
            return {"phi": None, "severity_avg": None, "density": None, "coverage": None, "trend": None}
        key = self.get_latest_image_key()
        if not key:
            return {"phi": None, "severity_avg": None, "density": None, "coverage": None, "trend": None}
        image_id = _image_id_from_object_key(key)
        return self.rdb.get_phi_for_image(image_id)


    # =====================================================
    # ===== ADDED: AUDIO ANALYTICS METHODS =====
    # =====================================================
    def get_audio_stats(self, time_range: str = 'all') -> Dict:
        """
        Get aggregated audio classification statistics.
        """
        time_filter = {
            'all': '',
            'hour': "AND r.started_at > NOW() - INTERVAL '1 hour'",
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'"
        }.get(time_range, '')

        query = f"""
            SELECT
                COUNT(*) AS total_files,
                SUM(CASE WHEN fa.head_is_another = true THEN 1 ELSE 0 END) AS unknown_count,
                AVG(fa.head_pred_prob) AS avg_confidence,
                AVG(fa.processing_ms) AS avg_processing_ms
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r
            ON fa.run_id = r.run_id
            WHERE 1=1 {time_filter}
        """
        results = self.run_query(query)
        return results[0] if results else {}

    def get_audio_distribution(self, time_range: str = 'all', limit: int = 10) -> List[Dict]:
        """
        Get distribution of audio classifications (for pie chart).
        """
        time_filter = {
            'all': '',
            'hour': "AND r.started_at > NOW() - INTERVAL '1 hour'",
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'"
        }.get(time_range, '')

        query = f"""
            SELECT
                fa.head_pred_label,
                COUNT(*) AS count
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r
            ON fa.run_id = r.run_id
            WHERE fa.head_pred_label IS NOT NULL
            {time_filter}
            GROUP BY fa.head_pred_label
            ORDER BY count DESC
            LIMIT {limit}
        """
        return self.run_query(query)

    def get_audio_confidence_by_class(self, time_range: str = 'all', limit: int = 10) -> List[Dict]:
        """
        Get average confidence levels by classification (for bar chart)
        Returns:
            List of dicts with 'head_pred_label' and 'avg_confidence' keys
        """
        time_filter = {
            'all': '',
            'hour': "AND r.started_at > NOW() - INTERVAL '1 hour'",
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'"
        }.get(time_range, '')
        query = f"""
            SELECT
                head_pred_label,
                AVG(head_pred_prob) as avg_confidence
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r ON fa.run_id = r.run_id
            WHERE head_pred_label IS NOT NULL
              AND head_pred_prob IS NOT NULL
              {time_filter}
            GROUP BY head_pred_label
            ORDER BY avg_confidence DESC
            LIMIT {limit}
        """
        return self.run_query(query)
    
    def get_audio_confidence_by_class(self, time_range: str = 'all', limit: int = 10) -> List[Dict]:
        """
        Get average confidence levels by classification (for bar chart).
        """
        time_filter = {
            'all': '',
            'hour': "AND r.started_at > NOW() - INTERVAL '1 hour'",
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'"
        }.get(time_range, '')

        query = f"""
            SELECT
                fa.head_pred_label,
                AVG(fa.head_pred_prob) AS avg_confidence
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r
            ON fa.run_id = r.run_id
            WHERE fa.head_pred_label IS NOT NULL
            AND fa.head_pred_prob IS NOT NULL
            {time_filter}
            GROUP BY fa.head_pred_label
            ORDER BY avg_confidence DESC
            LIMIT {limit}
        """
        return self.run_query(query)

    def get_audio_critical_events(self, time_range: str = 'day', limit: int = 100) -> List[Dict]:
        """
        Get critical sound events (fire, screaming, shotgun, predatory animals)
        Args:
            time_range: 'hour', 'day', 'week'
            limit: Maximum number of events to return
        Returns:
            List of critical event detections with timestamps
        """
        time_filter = {
            'hour': "AND r.started_at > NOW() - INTERVAL '1 hour'",
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'"
        }.get(time_range, "AND r.started_at > NOW() - INTERVAL '24 hours'")
        query = f"""
            SELECT
                r.run_id,
                r.started_at,
                f.path as file_path,
                fa.head_pred_label as event_type,
                fa.head_pred_prob as confidence,
                fa.head_probs_json
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r ON fa.run_id = r.run_id
            JOIN agcloud_audio.files f ON fa.file_id = f.file_id
            WHERE fa.head_pred_label IN ('fire', 'screaming', 'shotgun', 'predatory_animals')
              {time_filter}
            ORDER BY r.started_at DESC, fa.head_pred_prob DESC
            LIMIT {limit}
        """
        return self.run_query(query)
    
    def get_audio_critical_events(self, time_range: str = 'day', limit: int = 100) -> List[Dict]:
        """
        Get critical sound events (fire, screaming, shotgun, predatory animals).
        """
        time_filter = {
            'hour': "AND r.started_at > NOW() - INTERVAL '1 hour'",
            'day':  "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'"
        }.get(time_range, "AND r.started_at > NOW() - INTERVAL '24 hours'")

        query = f"""
            SELECT
                r.run_id,
                r.started_at,
                snsc.file_name,
                snsc.key AS s3_key,
                sm.device_id,
                sm.capture_time,
                fa.head_pred_label AS event_type,
                fa.head_pred_prob  AS confidence,
                fa.head_probs_json
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r
            ON fa.run_id = r.run_id
            JOIN public.sound_new_sounds_connections snsc
            ON fa.file_id = snsc.id
            LEFT JOIN public.sounds_metadata sm
            ON snsc.file_name = sm.file_name
            WHERE fa.head_pred_label IN ('fire', 'screaming', 'shotgun', 'predatory_animals')
            {time_filter}
            ORDER BY r.started_at DESC, fa.head_pred_prob DESC
            LIMIT {limit}
        """
        return self.run_query(query)



    # =====================================================
    # ===== ADDED: HELPER METHODS FOR OTHER VIEWS =====
    # =====================================================
    def get_sensors(self) -> List[Dict]:
        """Get all sensors from the sensors table"""
        query = "SELECT * FROM sensors ORDER BY sensor_name"
        return self.run_query(query)
    def get_sensor_status(self, sensor_name: str) -> Dict:
        """Get status of a specific sensor"""
        query = "SELECT * FROM sensors WHERE sensor_name = %s"
        results = self.run_query(query, (sensor_name,))
        return results[0] if results else {}
    def get_alerts(self, limit: int = 50) -> List[Dict]:
        """Get recent alerts"""
        query = """
            SELECT * FROM alerts
            ORDER BY started_at DESC
            LIMIT %s
        """
        return self.run_query(query, (limit,))
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            query = "UPDATE alerts SET ack = true WHERE alert_id = %s"
            cursor.execute(query, (alert_id,))
            conn.commit()
            print(f"[DashboardApi] Alert {alert_id} acknowledged", flush=True)
            return True
        except Exception as e:
            print(f"[DashboardApi] Error acknowledging alert: {e}", flush=True)
            return False
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    def get_ripeness_stats(self) -> Dict:
        """Get ripeness prediction statistics"""
        query = """
            SELECT
                COUNT(*) as total_predictions,
                SUM(CASE WHEN ripeness_label = 'ripe' THEN 1 ELSE 0 END) as ripe_count,
                SUM(CASE WHEN ripeness_label = 'unripe' THEN 1 ELSE 0 END) as unripe_count,
                SUM(CASE WHEN ripeness_label = 'overripe' THEN 1 ELSE 0 END) as overripe_count
            FROM ripeness_predictions
        """
        results = self.run_query(query)
        return results[0] if results else {}