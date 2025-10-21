#!/usr/bin/env python3
import os
import json
import time
import uuid
import hashlib
from datetime import datetime, timezone
import paho.mqtt.client as mqtt # type: ignore

# ---- Configuration ----
IMAGES_DIR = os.getenv("IMAGES_DIR", "/data/images")
META_DIR = os.getenv("META_DIR", "/data/metadata")

MQTT_HOST_DATA = os.getenv("MQTT_HOST_DATA", "large-mosquitto")
MQTT_PORT_DATA = int(os.getenv("MQTT_PORT_DATA", "1885"))
MQTT_TOPIC_DATA = os.getenv("MQTT_TOPIC_DATA", "MQTT/imagery/air")
MQTT_HOST_META = os.getenv("MQTT_HOST_META", "mosquitto")
MQTT_PORT_META = int(os.getenv("MQTT_PORT_META", "1883"))
MQTT_TOPIC_META = os.getenv("MQTT_TOPIC_META", "dev-robot-images-keys")

CAMERA_ID = os.getenv("CAMERA_ID", "drone-01")
INTERVAL_CHECK = int(os.getenv("INTERVAL_CHECK", "10"))
INTERVAL_PUBLISH = int(os.getenv("INTERVAL_PUBLISH", "10"))
QOS = int(os.getenv("MQTT_QOS", "1"))

# ---- MQTT Setup ----
client_data = mqtt.Client(client_id=f"drone-simulator-{uuid.uuid4().hex[:6]}")
client_data.connect(MQTT_HOST_DATA, MQTT_PORT_DATA, keepalive=60)
client_data.loop_start()

# client = mqtt.Client(client_id=f"drone-simulator-{uuid.uuid4().hex[:6]}")
# client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
# client.loop_start()

client_meta = mqtt.Client(client_id=f"drone-simulator-{uuid.uuid4().hex[:6]}")
client_meta.connect(MQTT_HOST_META, MQTT_PORT_META, keepalive=60)
client_meta.loop_start()


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

def publish_image(image_path):
    meta_data = load_metadata_for(image_path)
    payload = json.dumps(meta_data, ensure_ascii=False)
    with open(image_path, "rb") as f:
                data = f.read()
    client_data.publish(MQTT_TOPIC_DATA, payload=data, qos=QOS)
    client_meta.publish(MQTT_TOPIC_META, payload, qos=QOS)
    print(f"Published message for image: {meta_data['image_name']}", flush=True)


def get_all_images():
    exts = {".jpg", ".jpeg", ".png", ".tif"}
    return [os.path.join(IMAGES_DIR, f)
            for f in sorted(os.listdir(IMAGES_DIR))
            if os.path.splitext(f)[1].lower() in exts]

def main():
    print(f"Drone simulator started | Broker: {MQTT_HOST_DATA}:{MQTT_PORT_DATA} | Topic: {MQTT_TOPIC_DATA}")
    print(f"Drone simulator started | Broker: {MQTT_HOST_META}:{MQTT_PORT_META} | Topic: {MQTT_TOPIC_META}")
    sent_hashes = set()

    while True:
        all_imgs = get_all_images()
        new_imgs = [p for p in all_imgs if sha256_hex(p) not in sent_hashes]

        if not new_imgs:
            print("No new images. Checking again...")
            sent_hashes.clear() # for reapiting the images
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
        client_data.loop_stop()
        client_data.disconnect()
        client_meta.loop_stop()
        client_meta.disconnect()
