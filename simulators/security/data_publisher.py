# #!/usr/bin/env python3
# import os
# import json
# import time
# import uuid
# import hashlib
# import mimetypes
# from datetime import datetime, timezone
# import paho.mqtt.client as mqtt

# # ---- Configuration ----
# IMAGES_DIR = os.getenv("IMAGES_DIR", "/data/images")
# META_DIR = os.getenv("META_DIR", "/data/metadata")

# MQTT_HOST_DATA = os.getenv("MQTT_HOST_DATA", "large-mosquitto")
# MQTT_PORT_DATA = int(os.getenv("MQTT_PORT_DATA", "1885"))
# MQTT_TOPIC_DATA = os.getenv("MQTT_TOPIC_DATA", "MQTT/imagery/security")

# MQTT_HOST_META = os.getenv("MQTT_HOST_META", "mosquitto")
# MQTT_PORT_META = int(os.getenv("MQTT_PORT_META", "1883"))
# MQTT_TOPIC_META = os.getenv("MQTT_TOPIC_META", "dev-security-images-keys")

# CAMERA_ID = os.getenv("CAMERA_ID", "CAM-482A")
# INTERVAL_CHECK = int(os.getenv("INTERVAL_CHECK", "10"))
# INTERVAL_PUBLISH = int(os.getenv("INTERVAL_PUBLISH", "10"))
# QOS = int(os.getenv("MQTT_QOS", "1"))

# # ---- MQTT Setup ----
# client_images = mqtt.Client(client_id=f"camera-simulator-img-{uuid.uuid4().hex[:6]}")
# client_images.connect(MQTT_HOST_DATA, MQTT_PORT_DATA, keepalive=60)
# client_images.loop_start()

# client_meta = mqtt.Client(client_id=f"camera-simulator-meta-{uuid.uuid4().hex[:6]}")
# client_meta.connect(MQTT_HOST_META, MQTT_PORT_META, keepalive=60)
# client_meta.loop_start()

# # ---- Helpers ----
# def sha256_hex(path: str):
#     with open(path, "rb") as f:
#         return hashlib.sha256(f.read()).hexdigest()

# def iso_utc():
#     return datetime.utcnow().replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# def load_metadata_for(img_name):
#     base = os.path.splitext(os.path.basename(img_name))[0]
#     meta_path = os.path.join(META_DIR, f"{base}.json")
#     if os.path.exists(meta_path):
#         with open(meta_path, "r", encoding="utf-8") as f:
#             return json.load(f)
#     return {}

# def generate_new_name(ext=".jpg",camera_id = CAMERA_ID):
#     timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
#     return f"{camera_id}_{timestamp}{ext}"

# # ---- Core ----
# def publish_image(image_path):
#     ext = os.path.splitext(image_path)[1].lower()
#     meta_data = load_metadata_for(image_path)
#     camera_id = meta_data["camera_id"] or CAMERA_ID
#     new_file_name = generate_new_name(ext,camera_id)
#     meta_data["file_name"] = new_file_name
#     meta_data["capture_time"] = iso_utc()

#     with open(image_path, "rb") as f:
#         data = f.read()

#     timestamp_ms = int(time.time() * 1000)

#     # Automatically detect content type based on file extension
#     guessed_type, _ = mimetypes.guess_type(image_path)
#     if guessed_type:
#         content_type = guessed_type.replace("/", "_")  # e.g. image/jpeg → image_jpeg
#     else:
#         content_type = "application_octet-stream"

#     topic = f"{MQTT_TOPIC_DATA}/{timestamp_ms}/{content_type}/{new_file_name}"
#     client_images.publish(topic, payload=data, qos=QOS)
#     payload = json.dumps(meta_data, ensure_ascii=False)
#     client_meta.publish(MQTT_TOPIC_META, payload, qos=QOS)

#     print(f"Published image: {new_file_name} | topic: {topic} | type: {guessed_type}")

# def get_all_images():
#     exts = {".jpg", ".jpeg", ".png", ".tif"}
#     return [os.path.join(IMAGES_DIR, f)
#             for f in sorted(os.listdir(IMAGES_DIR))
#             if os.path.splitext(f)[1].lower() in exts]

# def main():
#     print("Camera simulator started")
#     print(f"  Images broker: {MQTT_HOST_DATA}:{MQTT_PORT_DATA} | topic: {MQTT_TOPIC_DATA}")
#     print(f"  Metadata broker: {MQTT_HOST_META}:{MQTT_PORT_META} | topic: {MQTT_TOPIC_META}")
#     sent_hashes = set()

#     while True:
#         all_imgs = get_all_images()
#         new_imgs = [p for p in all_imgs if sha256_hex(p) not in sent_hashes]

#         if not new_imgs:
#             print("No new images. Checking again...")
#             sent_hashes.clear()
#             time.sleep(INTERVAL_CHECK)
#             continue

#         for img in new_imgs:
#             publish_image(img)
#             sent_hashes.add(sha256_hex(img))
#             time.sleep(INTERVAL_PUBLISH)

#         print("Cycle completed. Restarting...")

# if __name__ == "__main__":
#     try:
#         main()
#     except KeyboardInterrupt:
#         print("Stopped manually.")
#         client_images.loop_stop()
#         client_images.disconnect()
#         client_meta.loop_stop()
#         client_meta.disconnect()




#!/usr/bin/env python3
import os
import json
import time
import uuid
import hashlib
import mimetypes
import threading
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
SECURITY_DIR = os.getenv("SECURITY_DIR", "/security")

MQTT_HOST_DATA = os.getenv("MQTT_HOST_DATA", "large-mosquitto")
MQTT_PORT_DATA = int(os.getenv("MQTT_PORT_DATA", "1885"))
MQTT_TOPIC_DATA = os.getenv("MQTT_TOPIC_DATA", "MQTT/imagery/security")

MQTT_HOST_META = os.getenv("MQTT_HOST_META", "mosquitto")
MQTT_PORT_META = int(os.getenv("MQTT_PORT_META", "1883"))
MQTT_TOPIC_META = os.getenv("MQTT_TOPIC_META", "dev-security-images-keys")

INTERVAL_PUBLISH = int(os.getenv("INTERVAL_PUBLISH", "10"))
QOS = int(os.getenv("MQTT_QOS", "1"))


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def sha256_hex(path: str):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def iso_utc():
    return datetime.utcnow().replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_new_name(ext=".jpg", camera_id="UNKNOWN"):
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"{camera_id}_{timestamp}{ext}"


def load_metadata_for(img_path, metadata_dir):
    base = os.path.splitext(os.path.basename(img_path))[0]
    meta_path = os.path.join(metadata_dir, f"{base}.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_all_images(images_dir):
    exts = {".jpg", ".jpeg", ".png", ".tif"}
    return [
        os.path.join(images_dir, f)
        for f in sorted(os.listdir(images_dir))
        if os.path.splitext(f)[1].lower() in exts
    ]


# ─────────────────────────────────────────────
# Publishing logic
# ─────────────────────────────────────────────
def publish_image(image_path, metadata_dir, camera_id, client_images, client_meta):
    ext = os.path.splitext(image_path)[1].lower()
    meta_data = load_metadata_for(image_path, metadata_dir)
    meta_data["camera_id"] = camera_id
    new_file_name = generate_new_name(ext, camera_id)
    meta_data["file_name"] = new_file_name
    meta_data["capture_time"] = iso_utc()

    with open(image_path, "rb") as f:
        data = f.read()

    timestamp_ms = int(time.time() * 1000)

    guessed_type, _ = mimetypes.guess_type(image_path)
    if guessed_type:
        content_type = guessed_type.replace("/", "_")
    else:
        content_type = "application_octet-stream"

    topic = f"{MQTT_TOPIC_DATA}/{timestamp_ms}/{content_type}/{new_file_name}"
    client_images.publish(topic, payload=data, qos=QOS)

    payload = json.dumps(meta_data, ensure_ascii=False)
    client_meta.publish(MQTT_TOPIC_META, payload, qos=QOS)

    print(f"[{camera_id}] Published image: {new_file_name} | topic: {topic} | type: {guessed_type}")


# ─────────────────────────────────────────────
# Per-camera worker (single run)
# ─────────────────────────────────────────────
def camera_worker(camera_path):
    camera_id = os.path.basename(camera_path)
    images_dir = os.path.join(camera_path, "images")
    metadata_dir = os.path.join(camera_path, "metadata")

    if not os.path.isdir(images_dir):
        print(f"[{camera_id}] Skipping: no /images folder found")
        return
    if not os.path.isdir(metadata_dir):
        print(f"[{camera_id}] Warning: no /metadata folder found")

    # Create separate MQTT clients per camera
    client_images = mqtt.Client(client_id=f"{camera_id}-img-{uuid.uuid4().hex[:6]}")
    client_images.connect(MQTT_HOST_DATA, MQTT_PORT_DATA, keepalive=60)
    client_images.loop_start()

    client_meta = mqtt.Client(client_id=f"{camera_id}-meta-{uuid.uuid4().hex[:6]}")
    client_meta.connect(MQTT_HOST_META, MQTT_PORT_META, keepalive=60)
    client_meta.loop_start()

    print(f"[{camera_id}] Started publishing thread")

    try:
        all_imgs = get_all_images(images_dir)
        if not all_imgs:
            print(f"[{camera_id}] No images found, skipping.")
        else:
            for img in all_imgs:
                publish_image(img, metadata_dir, camera_id, client_images, client_meta)
                time.sleep(INTERVAL_PUBLISH)

        print(f"[{camera_id}] Finished publishing {len(all_imgs)} images.")
    except Exception as e:
        print(f"[{camera_id}] Error: {e}")
    finally:
        client_images.loop_stop()
        client_images.disconnect()
        client_meta.loop_stop()
        client_meta.disconnect()


# ─────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────
def main():
    print("Camera simulator (single-run mode, multi-camera parallel)")
    print(f"Root directory: {SECURITY_DIR}")

    if not os.path.isdir(SECURITY_DIR):
        print(f"❌ SECURITY_DIR does not exist: {SECURITY_DIR}")
        return

    camera_dirs = [
        os.path.join(SECURITY_DIR, d)
        for d in os.listdir(SECURITY_DIR)
        if os.path.isdir(os.path.join(SECURITY_DIR, d))
    ]

    if not camera_dirs:
        print("❌ No camera directories found.")
        return

    threads = []
    for cam_dir in camera_dirs:
        t = threading.Thread(target=camera_worker, args=(cam_dir,))
        t.start()
        threads.append(t)

    # Wait for all camera threads to finish
    for t in threads:
        t.join()

    print("✅ All cameras finished publishing. Exiting.")


if __name__ == "__main__":
    main()


