#!/usr/bin/env python3
import os, time, glob, random, pathlib
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

HOST = os.getenv("MQTT_HOST", "large-mosquitto")
PORT = int(os.getenv("MQTT_PORT", "1885"))
TOPIC_BASE = os.getenv("MQTT_TOPIC_BASE", "MQTT/imagery")
IMAGES_DIR = os.getenv("IMAGES_DIR", "/images")
CAMERA_ID  = os.getenv("CAMERA_ID", "camera-01")
LIMIT      = int(os.getenv("LIMIT", "0"))
SHUFFLE    = os.getenv("SHUFFLE", "1") in ("1","true","yes","on")
QOS        = int(os.getenv("MQTT_QOS", "2"))
DELAY_MS   = int(os.getenv("PUBLISH_DELAY_MS", "10"))

def content_type_for(path: str) -> str:
    ext = pathlib.Path(path).suffix.lower()
    if ext in (".jpg", ".jpeg"): return "image/jpeg"
    if ext == ".png":            return "image/png"
    if ext == ".bmp":            return "image/bmp"
    if ext == ".gif":            return "image/gif"
    if ext == ".mp4":            return "video/mp4"
    if ext == ".mov":            return "video/quicktime"
    if ext == ".mkv":            return "video/x-matroska"
    if ext == ".avi":            return "video/x-msvideo"
    return "application/octet-stream"

def ctype_to_safe(ctype: str) -> str:
    return ctype.replace("/", "_")

def main():
    paths = sorted(glob.glob(f"{IMAGES_DIR}/**/*.*", recursive=True))
    if SHUFFLE:
        random.shuffle(paths)
    if LIMIT > 0:
        paths = paths[:LIMIT]

    client = mqtt.Client(
        CallbackAPIVersion.VERSION2,
        client_id=f"pub-{int(time.time())}",
        protocol=mqtt.MQTTv5,
    )
    client.max_inflight_messages_set(1000)
    client.max_queued_messages_set(0)
    client.reconnect_delay_set(min_delay=1, max_delay=8)

    def on_connect(client, userdata, flags, reason_code, properties):
        print(f"Publisher connected rc={reason_code}, files={len(paths)}", flush=True)

    client.on_connect = on_connect
    client.connect(HOST, PORT, keepalive=60)
    client.loop_start()

    t0 = time.time()
    sent = 0
    for p in paths:
        try:
            with open(p, "rb") as f:
                data = f.read()
            ctype = content_type_for(p)
            ctype_safe = ctype_to_safe(ctype)
            ts_ms = int(time.time() * 1000)
            filename = pathlib.Path(p).name
            topic = f"{TOPIC_BASE}/{CAMERA_ID}/{ts_ms}/{ctype_safe}/{filename}"
            r = client.publish(topic, payload=data, qos=QOS)
            r.wait_for_publish()
            sent += 1
            if DELAY_MS > 0:
                time.sleep(DELAY_MS / 1000.0)
        except Exception as e:
            print(f"[WARN] failed to publish {p}: {e}", flush=True)

    elapsed = time.time() - t0
    rate = sent / elapsed if elapsed > 0 else sent
    print(f"Publisher done. Sent={sent}, elapsed={elapsed:.2f}s, rate={rate:.1f} imgs/s", flush=True)

    client.loop_stop()
    client.disconnect()

if __name__ == "__main__":
    main()

