# ---------- Imports ----------
import os, io, time, hashlib, threading, queue, signal, json, uuid, errno, pathlib, mimetypes
from datetime import datetime, timezone
from typing import Tuple
from urllib.parse import quote

import boto3
from botocore.config import Config as BotoConfig
from boto3.s3.transfer import TransferConfig

import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from mqtt_ingest.config import cfg
except ModuleNotFoundError:
    from config import cfg

# ---------- ENV ----------
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
AWS_ACCESS_KEY   = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
AWS_SECRET_KEY   = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
BUCKET           = os.getenv("S3_BUCKET", "imagery")

MQTT_BROKER      = os.getenv("MQTT_BROKER", "large-mosquitto")
CLIENT_ID        = os.getenv("MQTT_CLIENT_ID", "mqtt_ingest")
DEFAULT_PREFIX   = os.getenv("DEFAULT_PREFIX", "camera-01")

FORCE_DEVICE_ID  = (os.getenv("DEVICE_ID", "").strip() or None)

DB_API_BASE        = os.getenv("DB_API_BASE", "").strip()
DB_API_TOKEN       = os.getenv("DB_API_TOKEN", "").strip()
DB_API_AUTH_MODE   = os.getenv("DB_API_AUTH_MODE", "service").lower()
DB_API_TOKEN_FILE  = os.getenv("DB_API_TOKEN_FILE", "/app/secret/db_api_token")
DB_API_SERVICE_NAME= os.getenv("DB_API_SERVICE_NAME", "mqtt_ingest").strip() or "mqtt_ingest"
OUTBOX_DIR         = os.getenv("OUTBOX_DIR", "/app/outbox")
DUMMY_DB           = os.getenv("DUMMY_DB", "0") == "1"

INGEST_QUEUE_MAXSIZE = int(os.getenv("INGEST_QUEUE_MAXSIZE", "1000"))

# ---------- NUMERIC FROM CONFIG ----------
MP_THRESHOLD   = cfg.MP_THRESHOLD
PART_SIZE      = cfg.PART_SIZE
MAX_CONC       = cfg.MAX_CONC
MQTT_PORT      = cfg.MQTT_PORT
INGEST_WORKERS = cfg.INGEST_WORKERS

# ---------- MQTT SUBSCRIBE TOPIC ----------
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "MQTT/imagery/#")

# Add at the top with other ENV variables:

# ---------- Media Prefixes ----------
CAMERA_PREFIX = os.getenv("CAMERA_PREFIX", "camera")
MICROPHONE_PREFIX = os.getenv("MICROPHONE_PREFIX", "microphone")
ULTRA_DIR_PREFIX = os.getenv("ULTRA_DIR_PREFIX", "plants") 

# ---------- S3 ----------
s3 = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    config=BotoConfig(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        max_pool_connections=max(64, MAX_CONC * 2),
        retries={"max_attempts": 3, "mode": "standard"},
    ),
)

tx_cfg = TransferConfig(
    multipart_threshold=MP_THRESHOLD,
    multipart_chunksize=PART_SIZE,
    max_concurrency=MAX_CONC,
    use_threads=True,
)

# ---------- Helpers ----------
mimetypes.init()

def get_s3_etag(bucket: str, key: str) -> str | None:
    try:
        resp = s3.head_object(Bucket=bucket, Key=key)
        etag = resp.get("ETag")
        if isinstance(etag, str):
            return etag.strip('"')
    except Exception:
        pass
    return None

def now_ms() -> int:
    return int(time.time() * 1000)

def iso_utc(ts_ms: int | None = None) -> str:
    if ts_ms is None:
        return datetime.utcnow().replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def sha256_hex(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()

def stem(filename: str) -> str:
    base = os.path.basename(filename)
    root, _ = os.path.splitext(base)
    return root or uuid.uuid4().hex

def normalize_content_type(ctype: str, filename: str) -> str:
    if ctype and ctype != "application/octet-stream":
        return ctype
    guess, _ = mimetypes.guess_type(filename)
    return guess or "application/octet-stream"

def parse_topic(topic: str) -> dict:
    parts = [p for p in topic.split("/") if p]
    parts_lower = [p.lower() for p in parts]
    now = now_ms()
    result = {
        "camera": DEFAULT_PREFIX,  
        "publish_ts_ms": now,
        "content_type": "application/octet-stream",
        "filename": f"{now}.bin",
        "media_type": "image",
    }

    # --- detect namespace and offsets ---
    ns = None
    idx = -1
    # for cand in ("imagery", "sounds"):
    #     if cand in parts:
    #         ns, idx = cand, parts.index(cand)
    #         break
    if "imagery" in parts_lower:
        ns, idx = "imagery", parts_lower.index("imagery")
    elif any(p.startswith("sounds_ultra") for p in parts_lower): 
        ns, idx = "sounds_ultra", next(i for i, p in enumerate(parts_lower) if p.startswith("sounds_ultra"))
    elif "sounds" in parts_lower:
        ns, idx = "sounds", parts_lower.index("sounds")
        
    if ns == "imagery":
        # format: MQTT/imagery/<device>/<ts>/<ctype>/<filename>
        if len(parts) > idx + 1 and parts[idx + 1]:
            result["camera"] = parts[idx + 1]
        if len(parts) > idx + 2 and parts[idx + 2]:
            try:
                ts = int(parts[idx + 2])
                if ts > 0:
                    result["publish_ts_ms"] = ts
            except ValueError:
                pass
        if len(parts) > idx + 3 and parts[idx + 3]:
            result["content_type"] = parts[idx + 3].replace("_", "/")
        if len(parts) > idx + 4 and parts[idx + 4]:
            result["filename"] = parts[idx + 4]

    elif ns in ("sounds", "sounds_ultra"):
        if len(parts) > idx + 1 and parts[idx + 1]:
            try:
                ts = int(parts[idx + 1])
                if ts > 0:
                    result["publish_ts_ms"] = ts
            except ValueError:
                pass
        if len(parts) > idx + 2 and parts[idx + 2]:
            result["content_type"] = parts[idx + 2].replace("_", "/")
        if len(parts) > idx + 3 and parts[idx + 3]:
            result["filename"] = parts[idx + 3]

    # normalize + media type detect
    result["content_type"] = normalize_content_type(result["content_type"], result["filename"])
    ctype = result["content_type"].lower()
    if ctype.startswith("image/"):
        result["media_type"] = "image"
    elif ctype.startswith("video/"):
        result["media_type"] = "image"
    elif ctype.startswith("audio/") or "sounds" in ctype or "wav" in ctype or "mp3" in ctype:
        result["media_type"] = "sounds"
    else:
        ext = result["filename"].lower().rsplit(".", 1)[-1] if "." in result["filename"] else ""
        if ext in ("jpg","jpeg","png","gif","bmp","tiff","webp"):
            result["media_type"] = "image"
        elif ext in ("wav","mp3","ogg","flac","aac","m4a"):
            result["media_type"] = "sounds"
        else:
            result["media_type"] = "image"

    date_part = datetime.fromtimestamp(result["publish_ts_ms"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    device_id = result["camera"]

    if result["media_type"] == "sounds":
        if device_id.startswith(f"{CAMERA_PREFIX}-"):
            device_name = device_id.replace(f"{CAMERA_PREFIX}-", f"{MICROPHONE_PREFIX}-", 1)
        elif device_id.startswith(f"{MICROPHONE_PREFIX}-"):
            device_name = device_id
        else:
            device_name = f"{MICROPHONE_PREFIX}-{device_id}"
    else:
        if device_id.startswith(f"{CAMERA_PREFIX}-"):
            device_name = device_id
        elif device_id.startswith(f"{MICROPHONE_PREFIX}-"):
            device_name = device_id.replace(f"{MICROPHONE_PREFIX}-", f"{CAMERA_PREFIX}-", 1)
        else:
            device_name = f"{CAMERA_PREFIX}-{device_id}"

    # key = f"{result['media_type']}/{device_name}/{date_part}/{result['publish_ts_ms']}/{result['filename']}"
    is_ultra = ns == "sounds_ultra" 
    topdir = ULTRA_DIR_PREFIX if is_ultra else result["media_type"]  
    key = f"{topdir}/{device_name}/{date_part}/{result['publish_ts_ms']}/{result['filename']}"

    result["key"] = key
    result["device_id"] = device_name
    result["image_id"] = stem(result["filename"]) or uuid.uuid4().hex
    result["capture_ts_iso"] = iso_utc(result["publish_ts_ms"])
    return result

# ---------- Uploader ----------
def upload_bytes(key: str, data: bytes, content_type: str) -> str:
    checksum = sha256_hex(data)
    extra_args = {"Metadata": {"checksum-sha256": checksum}, "ContentType": content_type}
    if len(data) >= MP_THRESHOLD:
        bio = io.BytesIO(data)
        s3.upload_fileobj(bio, BUCKET, key, ExtraArgs=extra_args, Config=tx_cfg)
    else:
        s3.put_object(Bucket=BUCKET, Key=key, Body=data, **extra_args)
    return checksum

# ---------- Outbox ----------
def _ensure_dir(path: str):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

def _safe_file_id(meta: dict) -> str:
    image_id = meta.get("image_id") or meta.get("metadata", {}).get("image_id")
    if not image_id:
        image_id = stem(meta.get("object_key", "") or uuid.uuid4().hex)
    return str(image_id).replace("/", "_")

def save_to_outbox(meta: dict) -> None:
    try:
        _ensure_dir(OUTBOX_DIR)
        file_id = _safe_file_id(meta)
        path = os.path.join(OUTBOX_DIR, f"{file_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        print(f"[OUTBOX] saved {path}", flush=True)
    except Exception as e:
        print(f"[OUTBOX][ERROR] {e}", flush=True)

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
    print(f"[BOOTSTRAP] fetching service token from {base}", flush=True)
    url = _safe_join_url(base, "/auth/_dev_bootstrap")
    payload = {"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": True}
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code not in (200, 201):
                time.sleep(backoff * attempt)
                continue
            data = r.json()
            raw = (data.get("service_account", {}) or {}).get("raw_token") \
               or (data.get("service_account", {}) or {}).get("token")
            if raw and isinstance(raw, str) and raw.strip() and "***" not in raw:
                return raw.strip()
        except Exception:
            time.sleep(backoff * attempt)
    return None

def get_or_bootstrap_token() -> str | None:
    if DB_API_TOKEN and DB_API_TOKEN.lower() != "auto":
        print("[BOOTSTRAP] using DB_API_TOKEN from env", flush=True)
        return DB_API_TOKEN
    if not DB_API_BASE:
        print("[BOOTSTRAP][WARN] DB_API_BASE not set; cannot bootstrap token.", flush=True)
        return None
    token = _read_token_from_file(DB_API_TOKEN_FILE)
    if token:
        print(f"[BOOTSTRAP] using service token from {DB_API_TOKEN_FILE}", flush=True)

        return token
    token = _fetch_token_via_dev_bootstrap(DB_API_BASE)
    if token:
        _write_token_to_file(DB_API_TOKEN_FILE, token)
        print(f"[BOOTSTRAP] wrote service token to {DB_API_TOKEN_FILE}", flush=True)
        return token
    print("[BOOTSTRAP][ERROR] Failed to obtain service token (dev bootstrap).", flush=True)
    return None

# ---------- Web Service client ----------
_http = requests.Session()
svc_token = get_or_bootstrap_token()

if svc_token:
    if DB_API_AUTH_MODE == "service":
        _http.headers.update({"X-Service-Token": svc_token})
    else:
        _http.headers.update({"Authorization": f"Bearer {svc_token}"})
_http.headers.update({"Content-Type": "application/json"})
_http.mount("http://",  HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])))
_http.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])))

def write_db(meta: dict) -> bool:
    if DUMMY_DB:
        print(
            f"[DB-DUMMY] would POST to {DB_API_BASE or 'N/A'}: {json.dumps(meta, ensure_ascii=False)}",
            flush=True,
        )
        return True

    if not DB_API_BASE:
        print("[DB][WARN] DB_API_BASE not set; skipping DB write.", flush=True)
        return False

    base = DB_API_BASE.rstrip("/")
    try:
        r = _http.post(f"{base}/api/files", json=meta, timeout=10)
        if 200 <= r.status_code < 300:
            print("[DB] POST ok", flush=True)
            return True
        if r.status_code == 409:
            print("[DB] POST conflict, trying PUT...", flush=True)
            ok_key = quote(meta["object_key"], safe="/")
            url = f"{base}/api/files/{meta['bucket']}/{ok_key}"
            r = _http.put(url, json=meta, timeout=10)
            ok = 200 <= r.status_code < 300
            print(f"[DB] PUT {'ok' if ok else r.status_code}", flush=True)
            return ok

        print(f"[DB] POST failed: {r.status_code} {r.text[:200]}", flush=True)
        return False

    except requests.ConnectionError as e:
        print(f"[DB][WARN] API not reachable ({base}): {e}", flush=True)
        return False

    except requests.Timeout as e:
        print(f"[DB][WARN] API timeout ({base}): {e}", flush=True)
        return False

    except requests.RequestException as e:
        print(f"[DB][ERROR] {e}", flush=True)
        return False


# ---------- Worker Queue ----------
q_in: "queue.Queue[Tuple[str, bytes, int]]" = queue.Queue(maxsize=INGEST_QUEUE_MAXSIZE)
_shutdown = threading.Event()

def worker():
    while not _shutdown.is_set():
        try:
            topic, payload, _ = q_in.get(timeout=0.5)
        except queue.Empty:
            continue
        info = parse_topic(topic)
        key = info["key"]
        try:
            checksum = upload_bytes(key, payload, info["content_type"])
            s3_uri = f"s3://{BUCKET}/{key}"
            etag_real = get_s3_etag(BUCKET, key)
            device_id = FORCE_DEVICE_ID or None
            db_row = {
                "bucket": BUCKET,
                "object_key": key,
                "content_type": info["content_type"],
                "size_bytes": len(payload),
                "etag": etag_real or checksum,
                "device_id": device_id,
                "mission_id": info.get("mission_id"),
                "tile_id": info.get("tile_id"),
                "footprint": info.get("footprint_wkt"),
                "metadata": {
                    "image_id": info["image_id"],
                    "s3_uri": s3_uri,
                    "sha256": checksum,
                    "capture_ts": info["capture_ts_iso"],
                    "ingest_ts": iso_utc(),
                    "source_topic": topic,
                    "extra": info.get("extra"),
                },
            }

            ok = write_db(db_row)
            if not ok and not DUMMY_DB:
                save_to_outbox(db_row)
        except Exception as e:
            print(f"[ERROR] upload failed for key={key}: {e}", flush=True)
        finally:
            q_in.task_done()

# ---------- MQTT Callbacks (API v2) ----------
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe(MQTT_TOPIC, qos=1)
        print(f"Subscribed to {MQTT_TOPIC} at {MQTT_BROKER}:{MQTT_PORT}", flush=True)
    else:
        print(f"[ERROR] MQTT connect reason_code={reason_code}", flush=True)

def on_message(client, userdata, msg):
    print(f"[MQTT] received message: {msg.topic}, {len(msg.payload)} bytes")
    q_in.put((msg.topic, msg.payload, 0))

def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    print(f"MQTT disconnected reason_code={reason_code}", flush=True)

# ---------- Main ----------
def main():
    try:
        s3.head_bucket(Bucket=BUCKET)
    except Exception:
        s3.create_bucket(Bucket=BUCKET)

    for _ in range(max(2, INGEST_WORKERS)):
        threading.Thread(target=worker, daemon=True).start()

    client = mqtt.Client(
        CallbackAPIVersion.VERSION2,
        client_id=CLIENT_ID,
        protocol=mqtt.MQTTv5,
    )
    client.max_inflight_messages_set(1000)
    client.max_queued_messages_set(0)
    client.reconnect_delay_set(min_delay=1, max_delay=8)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()

    print(
        f"INGEST ready. mp_threshold={MP_THRESHOLD}, part={PART_SIZE}, conc={MAX_CONC}, workers={INGEST_WORKERS}",
        flush=True
    )

    def _stop(*_):
        _shutdown.set()
        client.loop_stop()
        client.disconnect()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        while not _shutdown.is_set():
            time.sleep(0.2)
    finally:
        q_in.join()
        print("INGEST stopped.", flush=True)

if __name__ == "__main__":
    main()
