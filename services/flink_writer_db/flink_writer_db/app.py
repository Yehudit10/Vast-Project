import os, json, pathlib, requests
from pyflink.common import Types
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.watermark_strategy import WatermarkStrategy
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------- ENV ----------
DB_API_BASE = os.getenv("DB_API_BASE", "http://db_api_service:8001")
DB_API_AUTH_MODE = os.getenv("DB_API_AUTH_MODE", "service")  
DB_API_TOKEN_FILE = os.getenv("DB_API_TOKEN_FILE", "/app/secrets/db_api_token")
DB_API_SERVICE_NAME = os.getenv("DB_API_SERVICE_NAME", "flink-writer-db")
DUMMY_DB = int(os.getenv("DUMMY_DB", "0")) == 1

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka:9092")
TOPICS = [t.strip() for t in os.getenv("TOPICS", "incidents.create,incidents.update").split(",") if t.strip()]


# ---------- Token Bootstrap ----------
def _safe_join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _read_token_from_file(path: str) -> str | None:
    try:
        p = pathlib.Path(path)
        if p.exists():
            t = p.read_text(encoding="utf-8").strip()
            return t or None
    except Exception:
        pass
    return None


def _write_token_to_file(path: str, token: str) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(token, encoding="utf-8")


def _fetch_token_via_dev_bootstrap(base: str, retries: int = 3, backoff: float = 0.8) -> str | None:
    url = _safe_join_url(base, "/auth/_dev_bootstrap")
    payload = {"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": True}
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code not in (200, 201):
                import time
                time.sleep(backoff * attempt)
                continue
            data = r.json()
            raw = (data.get("service_account", {}) or {}).get("raw_token") \
                or (data.get("service_account", {}) or {}).get("token")
            if raw and isinstance(raw, str) and raw.strip() and "***" not in raw:
                return raw.strip()
        except Exception:
            import time
            time.sleep(backoff * attempt)
    return None


def get_or_bootstrap_token() -> str | None:
    token = _read_token_from_file(DB_API_TOKEN_FILE)
    if token:
        return token
    if not DB_API_BASE:
        print("[BOOTSTRAP][WARN] DB_API_BASE not set; cannot bootstrap token.", flush=True)
        return None
    token = _fetch_token_via_dev_bootstrap(DB_API_BASE)
    if token:
        _write_token_to_file(DB_API_TOKEN_FILE, token)
        print(f"[BOOTSTRAP] wrote service token to {DB_API_TOKEN_FILE}", flush=True)
        return token
    print("[BOOTSTRAP][ERROR] Failed to obtain service token (dev bootstrap).", flush=True)
    return None


# ---------- HTTP client ----------
_http = requests.Session()
svc_token = get_or_bootstrap_token()
if svc_token:
    if DB_API_AUTH_MODE == "service":
        _http.headers.update({"X-Service-Token": svc_token})
    else:
        _http.headers.update({"Authorization": f"Bearer {svc_token}"})
_http.headers.update({"Content-Type": "application/json"})
_http.mount("http://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])))
_http.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])))


# ---------- DB Writer ----------
def write_to_db_api(topic: str, payload: dict) -> bool:
    """
    Write JSON payload to DB API based on Kafka topic naming:
      <table>.<action>

    Examples:
      "incidents.create" -> POST /api/incidents   (body = payload)
      "incidents.update" -> PATCH /api/incidents  (body = {"keys": {"incident_id": ...}, "data": {...}})
    """
    if DUMMY_DB:
        print(f"[DB-DUMMY] {topic}: {json.dumps(payload, ensure_ascii=False)[:250]}", flush=True)
        return True

    if not DB_API_BASE:
        print("[DB][WARN] DB_API_BASE not set; skipping DB write.", flush=True)
        return False

    # Parse topic
    parts = topic.split(".")
    if len(parts) < 2:
        print(f"[DB][WARN] Topic '{topic}' missing action suffix (.create/.update)", flush=True)
        return False

    table, action = parts[0], parts[1].lower()
    url = f"{DB_API_BASE.rstrip('/')}/api/{table}"

    # ─────────────── Decide method ───────────────
    if action in ("create", "post", "insert"):
        method = "POST"
        body = payload

    elif action in ("update", "patch"):
        method = "PATCH"

        # If already structured as {"keys": {...}, "data": {...}}, send as-is
        if isinstance(payload, dict) and "keys" in payload and "data" in payload:
            body = payload
        else:
            incident_id = payload.get("incident_id")
            if not incident_id:
                print(f"[DB][WARN] Missing 'incident_id' in payload for topic {topic}", flush=True)
                return False

            # Remove the key from update data
            data = {k: v for k, v in payload.items() if k != "incident_id"}

            body = {
                "keys": {"incident_id": incident_id},
                "data": data,
            }
    else:
        print(f"[DB][WARN] Unsupported action '{action}' in topic {topic}", flush=True)
        return False

    # ─────────────── Perform HTTP request ───────────────
    try:
        print(f"[DB] {method} {url} → {json.dumps(body, ensure_ascii=False)[:200]}", flush=True)
        r = _http.request(method, url, json=body, timeout=10)

        if 200 <= r.status_code < 300:
            print(f"[DB] {method} OK {topic}", flush=True)
            return True

        print(f"[DB] {method} failed ({topic}): {r.status_code} {r.text[:200]}", flush=True)
        return False

    except requests.RequestException as e:
        print(f"[DB][ERROR] {method} {url}: {e}", flush=True)
        return False





# ---------- Flink Job ----------
def handle_message(topic: str, raw: str) -> bool:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[WARN] skip invalid JSON on topic={topic}: {raw[:150]!r}", flush=True)
        return False
    ok = write_to_db_api(topic, data)
    return ok


def main():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(int(os.getenv("FLINK_PARALLELISM", "1")))

    for topic in TOPICS:
        print(f"[FLINK] Listening on topic: {topic}", flush=True)

        source = (
            KafkaSource.builder()
            .set_bootstrap_servers(KAFKA_BROKERS)
            .set_topics(topic)
            .set_group_id(f"flink-writer-db-{topic}")
            .set_value_only_deserializer(SimpleStringSchema())
            .build()
        )

        ds = env.from_source(source, WatermarkStrategy.no_watermarks(), f"kafka-{topic}")
        ds.map(lambda raw, t=topic: handle_message(t, raw), output_type=Types.BOOLEAN()).print()

    env.execute("flink-writer-db")


if __name__ == "__main__":
    main()
