# # import json
# # import time
# # import pathlib
# # import requests
# # from urllib.parse import quote
# # from requests.adapters import HTTPAdapter
# # from urllib3.util.retry import Retry
# # # ---------- CONFIG ----------
# # DB_API_BASE = "http://host.docker.internal:8001"
# # DB_API_AUTH_MODE = "service"
# # DB_API_TOKEN_FILE = "/app/secret/db_api_token"
# # DB_API_TOKEN = "auto"
# # DB_API_SERVICE_NAME = "GUI_H"
# # # ---------- TOKEN BOOTSTRAP ----------
# # def _safe_join_url(base: str, path: str) -> str:
# #     return f"{base.rstrip('/')}/{path.lstrip('/')}"
# # def _read_token_from_file(path: str) -> str | None:
# #     p = pathlib.Path(path)
# #     if p.exists():
# #         token = p.read_text(encoding="utf-8").strip()
# #         return token or None
# #     return None
# # def _fetch_token_via_dev_bootstrap(base: str, retries: int = 3, backoff: float = 0.8) -> str | None:
# #     url = _safe_join_url(base, "/auth/_dev_bootstrap")
# #     payload = {"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": True}
# #     for attempt in range(1, retries + 1):
# #         try:
# #             r = requests.post(url, json=payload, timeout=10)
# #             if r.status_code in (200, 201):
# #                 data = r.json()
# #                 raw = (data.get("service_account", {}) or {}).get("raw_token") \
# #                     or (data.get("service_account", {}) or {}).get("token")
# #                 if raw and isinstance(raw, str) and "***" not in raw:
# #                     return raw.strip()
# #         except Exception:
# #             time.sleep(backoff * attempt)
# #     return None
# # def get_or_bootstrap_token() -> str | None:
# #     print(f"[DEBUG] Checking for existing token file at: {DB_API_TOKEN_FILE}", flush=True)
# #     if DB_API_TOKEN and DB_API_TOKEN.lower() != "auto":
# #         print(f"[DEBUG] Using static token from config", flush=True)
# #         return DB_API_TOKEN
# #     token = _read_token_from_file(DB_API_TOKEN_FILE)
# #     if token:
# #         print(f"[DEBUG] Loaded token from {DB_API_TOKEN_FILE}", flush=True)
# #         return token
# #     print(f"[DEBUG] No existing token found, bootstrapping via {DB_API_BASE}/auth/_dev_bootstrap", flush=True)
# #     token = _fetch_token_via_dev_bootstrap(DB_API_BASE)
# #     if token:
# #         pathlib.Path(DB_API_TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
# #         pathlib.Path(DB_API_TOKEN_FILE).write_text(token, encoding="utf-8")
# #         print(f"[BOOTSTRAP] wrote token to {DB_API_TOKEN_FILE}", flush=True)
# #         return token
# #     print("[BOOTSTRAP][ERROR] Failed to obtain token.", flush=True)
# #     return None
# # # ---------- API CLIENT ----------
# # class DashboardApi:
# #     def __init__(self):
# #         self.base = DB_API_BASE.rstrip("/")
# #         self.http = requests.Session()
# #         token = get_or_bootstrap_token()
# #         if token:
# #             if DB_API_AUTH_MODE == "service":
# #                 self.http.headers.update({"X-Service-Token": token})
# #             else:
# #                 self.http.headers.update({"Authorization": f"Bearer {token}"})
# #         self.http.headers.update({"Content-Type": "application/json"})
# #         self.http.mount("http://",  HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])))
# #         self.http.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])))
# #     # ---------- METHODS ----------
# #     def list_devices(self, model: str | None = None) -> list[dict]:
# #         url = f"{self.base}/api/devices"
# #         if model:
# #             url += f"?model={model}"
# #         try:
# #             r = self.http.get(url, timeout=10)
# #             if r.status_code == 200:
# #                 return r.json()
# #             print(f"[API ERROR] {r.status_code}: {r.text[:100]}")
# #         except Exception as e:
# #             print(f"[API FAIL] {e}")
# #         return []


# # services/plant_stress/src/db_api_client.py
# # services/plant_stress/src/db_api_client.py
# import os, pathlib, time, requests

# DB_API_BASE = os.getenv("DB_API_BASE", "http://db_api_service:8001").rstrip("/")
# DB_API_AUTH_MODE = os.getenv("DB_API_AUTH_MODE", "service")
# DB_API_TOKEN_FILE = os.getenv("DB_API_TOKEN_FILE", "/tmp/db_api_token")
# DB_API_TOKEN = os.getenv("DB_API_TOKEN", "auto")
# DB_API_SERVICE_NAME = os.getenv("DB_API_SERVICE_NAME", "plant_stress")

# def _join(b, p): 
#     return f"{b.rstrip('/')}/{p.lstrip('/')}"

# def _read_token(path):
#     p = pathlib.Path(path)
#     return p.read_text(encoding="utf-8").strip() if p.exists() else None

# def _bootstrap_token(base, retries=3, backoff=0.8):
#     url = _join(base, "/auth/_dev_bootstrap")
#     payload = {"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": True}
#     for i in range(1, retries+1):
#         try:
#             r = requests.post(url, json=payload, timeout=10)
#             if r.status_code in (200, 201):
#                 sa = (r.json().get("service_account", {}) or {})
#                 raw = sa.get("raw_token") or sa.get("token")
#                 if raw and isinstance(raw, str) and "***" not in raw:
#                     return raw.strip()
#         except Exception:
#             time.sleep(backoff * i)
#     return None

# def get_or_bootstrap_token():
#     if DB_API_TOKEN and DB_API_TOKEN.lower() != "auto":
#         return DB_API_TOKEN
#     tok = _read_token(DB_API_TOKEN_FILE)
#     if tok:
#         return tok
#     tok = _bootstrap_token(DB_API_BASE)
#     if tok:
#         pathlib.Path(DB_API_TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
#         pathlib.Path(DB_API_TOKEN_FILE).write_text(tok, encoding="utf-8")
#         print(f"[BOOTSTRAP] wrote token to {DB_API_TOKEN_FILE}", flush=True)
#         return tok
#     print("[BOOTSTRAP][ERROR] Failed to obtain token.", flush=True)
#     return None

# # ---- requests.Session() גלובלי ----
# _SESSION = None
# def get_session():
#     global _SESSION
#     if _SESSION is None:
#         s = requests.Session()
#         tok = get_or_bootstrap_token()
#         if tok:
#             if DB_API_AUTH_MODE == "service":
#                 s.headers.update({"X-Service-Token": tok})
#             else:
#                 s.headers.update({"Authorization": f"Bearer {tok}"})
#         s.headers.update({"Content-Type": "application/json"})
#         _SESSION = s
#     return _SESSION

# FILES_POST = "/api/files"
# FILES_PUT_TPL = "/api/files/{bucket}/{object_key}"

# def _variants_for_create(meta: dict):
#     """נפיק כמה וריאציות פייפ/load נפוצות ל-POST /api/files"""
#     b = meta.get("bucket"); k = meta.get("object_key")
#     mime = meta.get("mime", "audio/wav")
#     tags = meta.get("tags", [])
#     mdata = {
#         "service":         meta.get("service"),
#         "timestamp":       meta.get("timestamp"),
#         "predicted_class": meta.get("predicted_class"),
#         "confidence":      meta.get("confidence"),
#     }
#     return [
#         {"bucket": b, "object_key": k, "mime": mime, "tags": tags, "metadata": mdata},
#         {"bucket": b, "object_key": k, "content_type": mime, "tags": tags, "metadata": mdata},
#         {"bucket": b, "object_key": k, "mime": mime, "labels": tags, "metadata": mdata},
#         {"bucket": b, "object_key": k, "mime": mime, "meta": mdata},
#         {"bucket": b, "object_key": k},  # מינימלי מאוד (ייתכן שהסכמה דורשת עוד – נבדוק 422)
#     ]

# def _variants_for_update(meta: dict):
#     """וריאציות PUT /api/files/{bucket}/{object_key}"""
#     mime = meta.get("mime", "audio/wav")
#     tags = meta.get("tags", [])
#     mdata = {
#         "service":         meta.get("service"),
#         "timestamp":       meta.get("timestamp"),
#         "predicted_class": meta.get("predicted_class"),
#         "confidence":      meta.get("confidence"),
#     }
#     return [
#         {"mime": mime, "tags": tags, "metadata": mdata},
#         {"content_type": mime, "tags": tags, "metadata": mdata},
#         {"metadata": mdata},
#         {"tags": tags},
#     ]

# def write_db_entry(meta: dict) -> bool:
#     """
#     רושם/מעדכן רשומת קובץ + מטא-דטה ב-DB API דרך Files API.
#     """
#     s = get_session()
#     b = meta.get("bucket"); k = meta.get("object_key")
#     if not b or not k:
#         print("[API ERROR] meta must include 'bucket' and 'object_key'")
#         return False

#     # 1) נסה POST /api/files עם כמה וריאציות
#     for payload in _variants_for_create(meta):
#         try:
#             r = s.post(_join(DB_API_BASE, FILES_POST), json=payload, timeout=15)
#             if r.status_code in (200, 201):
#                 return True
#             # אם האובייקט כבר קיים או הסכמה לא תואמת – ננסה וריאציה אחרת / נגלוש ל-PUT
#         except Exception as e:
#             print(f"[API ERROR] POST /api/files: {e}")

#     # 2) PUT /api/files/{bucket}/{object_key} (upsert/update)
#     path = FILES_PUT_TPL.format(bucket=b, object_key=k)
#     for payload in _variants_for_update(meta):
#         try:
#             r = s.put(_join(DB_API_BASE, path), json=payload, timeout=15)
#             if r.status_code in (200, 201):
#                 return True
#             # ננסה וריאציה הבאה
#         except Exception as e:
#             print(f"[API ERROR] PUT {path}: {e}")

#     try:
#         print(f"[API ERROR] all variants failed for {b}/{k}. Last status={r.status_code} body={r.text[:300]}")
#     except Exception:
#         pass
#     return False

