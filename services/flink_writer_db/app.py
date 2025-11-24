import os, json, pathlib, requests, queue, threading
from pyflink.common import Types
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.common import Configuration
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ------------------------- ENV -------------------------

DB_API_BASE = os.getenv("DB_API_BASE", "http://db_api_service:8001")
DB_API_AUTH_MODE = os.getenv("DB_API_AUTH_MODE", "service")
DB_API_TOKEN_FILE = os.getenv("DB_API_TOKEN_FILE", "/opt/app/secrets/db_api_token")
DB_API_SERVICE_NAME = os.getenv("DB_API_SERVICE_NAME", "flink-writer-db")
DUMMY_DB = int(os.getenv("DUMMY_DB", "0")) == 1

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka:9092")
TOPICS = [t.strip() for t in os.getenv(
    "TOPICS",
    "sensor_anomalies,alerts,image_new_aerial_connections,sound_new_sounds_connections,"
    "sound_new_plants_connections,sounds_metadata,sounds_ultra_metadata"
).split(",") if t.strip()]

# ------------------------- TOKEN BOOTSTRAP -------------------------

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
                import time; time.sleep(backoff * attempt)
                continue
            data = r.json()
            raw = (
                (data.get("service_account", {}) or {}).get("raw_token")
                or (data.get("service_account", {}) or {}).get("token")
            )
            if raw and isinstance(raw, str) and raw.strip() and "***" not in raw:
                return raw.strip()
        except Exception:
            import time; time.sleep(backoff * attempt)
    return None

def get_or_bootstrap_token() -> str | None:
    token = _read_token_from_file(DB_API_TOKEN_FILE)
    if token:
        return token
    if not DB_API_BASE:
        print("[BOOTSTRAP][WARN] DB_API_BASE not set", flush=True)
        return None
    token = _fetch_token_via_dev_bootstrap(DB_API_BASE)
    if token:
        _write_token_to_file(DB_API_TOKEN_FILE, token)
        print(f"[BOOTSTRAP] wrote service token to {DB_API_TOKEN_FILE}", flush=True)
        return token
    print("[BOOTSTRAP][ERROR] Failed to obtain service token", flush=True)
    return None

# ------------------------- SHARED HEADERS -------------------------

shared_headers = {"Content-Type": "application/json"}
token_value = get_or_bootstrap_token()

if token_value:
    if DB_API_AUTH_MODE == "service":
        shared_headers["X-Service-Token"] = token_value
    else:
        shared_headers["Authorization"] = f"Bearer {token_value}"

# ------------------------- PER-TOPIC WORKERS -------------------------

topic_workers = {}
topic_queues = {}
topic_worker_counts = {}
topic_scale_locks = {}

MAX_WORKERS_PER_TOPIC = 5
MIN_WORKERS_PER_TOPIC = 1
SCALE_UP_THRESHOLD = 8000
SCALE_DOWN_THRESHOLD = 2000

def build_retry_session(headers: dict):
    s = requests.Session()
    s.headers.update(headers)

    retry_cfg = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_cfg)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update(headers)
    return s

def start_topic_worker(topic: str):
    if topic not in topic_worker_counts:
        topic_worker_counts[topic] = 0
        topic_scale_locks[topic] = threading.Lock()

    if topic not in topic_queues:
        topic_queues[topic] = queue.Queue(maxsize=30000)

    q = topic_queues[topic]

    def spawn_worker():
        session = build_retry_session(shared_headers)
        base = DB_API_BASE.rstrip("/")
        url = f"{base}/api/tables/{topic}"

        def worker_loop():
            while True:
                payload = q.get()
                try:
                    r = session.post(url, json=payload, timeout=10)
                    if not (200 <= r.status_code < 300):
                        print(f"[DB][{topic}] Error {r.status_code}: {r.text[:150]}")
                except Exception as e:
                    print(f"[DB][{topic}] Exception: {e}")
                finally:
                    q.task_done()

        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()
        topic_worker_counts[topic] += 1

    if topic_worker_counts[topic] == 0:
        spawn_worker()

    if topic not in topic_workers:
        def autoscaler():
            while True:
                size = q.qsize()
                with topic_scale_locks[topic]:
                    if size > SCALE_UP_THRESHOLD and topic_worker_counts[topic] < MAX_WORKERS_PER_TOPIC:
                        spawn_worker()

                    if size < SCALE_DOWN_THRESHOLD and topic_worker_counts[topic] > MIN_WORKERS_PER_TOPIC:
                        topic_worker_counts[topic] = max(topic_worker_counts[topic] - 1, MIN_WORKERS_PER_TOPIC)

                import time
                time.sleep(2)

        t = threading.Thread(target=autoscaler, daemon=True)
        t.start()
        topic_workers[topic] = t

def enqueue_for_db(topic: str, payload: dict) -> bool:
    if DUMMY_DB:
        print(f"[DB-DUMMY] {topic}: {json.dumps(payload)[:200]}")
        return True

    start_topic_worker(topic)
    q = topic_queues[topic]

    try:
        q.put_nowait(payload)
        return True
    except queue.Full:
        print(f"[WARN][{topic}] queue full - dropping")
        return False

# ------------------------- MESSAGE HANDLER -------------------------

def handle_message(topic: str, raw: str) -> bool:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[WARN] invalid JSON on topic={topic}")
        return False
    return enqueue_for_db(topic, data)

# ------------------------- MAIN FLINK JOB -------------------------

def main():
    conf = Configuration()
    conf.set_string("restart-strategy", "fixed-delay")
    conf.set_string("restart-strategy.fixed-delay.attempts", "9999")
    conf.set_string("restart-strategy.fixed-delay.delay", "5 s")

    env = StreamExecutionEnvironment.get_execution_environment(conf)
    env.set_parallelism(int(os.getenv("FLINK_PARALLELISM", "1")))

    for topic in TOPICS:
        print(f"[FLINK] Listening on: {topic}", flush=True)

        source = (
            KafkaSource.builder()
            .set_bootstrap_servers(KAFKA_BROKERS)
            .set_topics(topic)
            .set_group_id(f"flink-writer-db-{topic}")
            .set_value_only_deserializer(SimpleStringSchema())
            .set_property("allow.auto.create.topics", "true")
            .set_property("metadata.max.age.ms", "10000")
            .build()
        )

        ds = env.from_source(
            source,
            WatermarkStrategy.no_watermarks(),
            f"kafka-{topic}"
        )

        ds.map(
            lambda raw, t=topic: handle_message(t, raw),
            output_type=Types.BOOLEAN()
        ).print()

    env.execute("flink-writer-db")

if __name__ == "__main__":
    main()
