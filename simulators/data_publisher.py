#!/usr/bin/env python3
import os
import json
import time
import uuid
import hashlib
import mimetypes
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# ---- Configuration ----
IMAGES_DIR = os.getenv("IMAGES_DIR", "/data/images")
META_DIR = os.getenv("META_DIR", "/data/metadata")

MQTT_HOST_DATA = os.getenv("MQTT_HOST_DATA", "large-mosquitto")
MQTT_PORT_DATA = int(os.getenv("MQTT_PORT_DATA", "1885"))
MQTT_TOPIC_DATA = os.getenv("MQTT_TOPIC_DATA", "MQTT/imagery/air")

MQTT_HOST_META = os.getenv("MQTT_HOST_META", "mosquitto")
MQTT_PORT_META = int(os.getenv("MQTT_PORT_META", "1883"))
MQTT_TOPIC_META = os.getenv("MQTT_TOPIC_META", "dev-aerial-images-keys")

CAMERA_ID = os.getenv("CAMERA_ID", "DRN-482A")
INTERVAL_CHECK = int(os.getenv("INTERVAL_CHECK", "10"))
INTERVAL_PUBLISH = int(os.getenv("INTERVAL_PUBLISH", "10"))
QOS = int(os.getenv("MQTT_QOS", "1"))

# ---- MQTT Setup ----
client_images = mqtt.Client(client_id=f"drone-simulator-img-{uuid.uuid4().hex[:6]}")
client_images.connect(MQTT_HOST_DATA, MQTT_PORT_DATA, keepalive=60)
client_images.loop_start()

client_meta = mqtt.Client(client_id=f"drone-simulator-meta-{uuid.uuid4().hex[:6]}")
client_meta.connect(MQTT_HOST_META, MQTT_PORT_META, keepalive=60)
client_meta.loop_start()

# ---- Helpers ----
def sha256_hex(path: str):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def iso_utc():
    return datetime.utcnow().replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def load_metadata_for(img_name):
    base = os.path.splitext(os.path.basename(img_name))[0]
    meta_path = os.path.join(META_DIR, f"{base}.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def generate_new_name(ext=".jpg"):
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"{CAMERA_ID}_{timestamp}{ext}"

# ---- Core ----
def publish_image(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    meta_data = load_metadata_for(image_path)
    new_file_name = generate_new_name(ext)
    meta_data["file_name"] = new_file_name
    meta_data["capture_time"] = iso_utc()

    with open(image_path, "rb") as f:
        data = f.read()

    timestamp_ms = int(time.time() * 1000)

    # Automatically detect content type based on file extension
    guessed_type, _ = mimetypes.guess_type(image_path)
    if guessed_type:
        content_type = guessed_type.replace("/", "_")  # e.g. image/jpeg → image_jpeg
    else:
        content_type = "application_octet-stream"

    topic = f"{MQTT_TOPIC_DATA}/{timestamp_ms}/{content_type}/{new_file_name}"
    client_images.publish(topic, payload=data, qos=QOS)

    payload = json.dumps(meta_data, ensure_ascii=False)
    client_meta.publish(MQTT_TOPIC_META, payload, qos=QOS)

    print(f"Published image: {new_file_name} | topic: {topic} | type: {guessed_type}")

def get_all_images():
    exts = {".jpg", ".jpeg", ".png", ".tif"}
    return [os.path.join(IMAGES_DIR, f)
            for f in sorted(os.listdir(IMAGES_DIR))
            if os.path.splitext(f)[1].lower() in exts]

def main():
    print("Drone simulator started")
    print(f"  Images broker: {MQTT_HOST_DATA}:{MQTT_PORT_DATA} | topic: {MQTT_TOPIC_DATA}")
    print(f"  Metadata broker: {MQTT_HOST_META}:{MQTT_PORT_META} | topic: {MQTT_TOPIC_META}")
    sent_hashes = set()

    while True:
        all_imgs = get_all_images()
        new_imgs = [p for p in all_imgs if sha256_hex(p) not in sent_hashes]

        if not new_imgs:
            print("No new images. Checking again...")
            sent_hashes.clear()
            time.sleep(INTERVAL_CHECK)
            continue

        for img in new_imgs:
            publish_image(img)
            sent_hashes.add(sha256_hex(img))
            time.sleep(INTERVAL_PUBLISH)

        print("Cycle completed. Restarting...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped manually.")
        client_images.loop_stop()
        client_images.disconnect()
        client_meta.loop_stop()
        client_meta.disconnect()
