import os
import time
from minio import Minio
from minio.error import S3Error
import paho.mqtt.client as mqtt

# --- MinIO connection details ---
MINIO_ENDPOINT = "localhost:9001"  # MinIO server address (change if remote)
ACCESS_KEY = "minioadmin"
SECRET_KEY = "minioadmin123"
BUCKET_NAME = "audio-files"  # The MinIO bucket where we will upload files

# --- Connecting to MinIO ---
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=ACCESS_KEY,
    secret_key=SECRET_KEY,
    secure=False  # Set to True if using TLS/SSL
)

# --- MQTT connection details ---
MQTT_BROKER = "localhost"  # Address of the MQTT broker (Mosquitto)
MQTT_PORT = 1883           # Default MQTT port

# --- MQTT Topics ---
MQTT_AUDIO_TOPIC = "audio-files/audio/uploaded"
MQTT_JSON_TOPIC = "audio-files/json/uploaded"

# --- Ensure the bucket exists, if not, create it ---
if not minio_client.bucket_exists(BUCKET_NAME):
    minio_client.make_bucket(BUCKET_NAME)

# --- Local directories ---
LOCAL_AUDIO_DIR = "./mqtt_images/data/real_images/audio"  # Folder where the audio files are stored
LOCAL_JSON_DIR = "./mqtt_images/data/real_images/json"   # Folder where the JSON files are stored

# --- Valid file formats ---
valid_audio_formats = [".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"]
valid_json_formats = [".json"]

# --- Function to check if the file has a valid format ---
def is_valid_audio_format(file_name):
    return any(file_name.endswith(ext) for ext in valid_audio_formats)

def is_valid_json_format(file_name):
    return any(file_name.endswith(ext) for ext in valid_json_formats)

# --- MQTT Client Setup ---
mqtt_client = mqtt.Client()

# --- Connect to MQTT Broker ---
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)

# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")

mqtt_client.on_connect = on_connect
mqtt_client.loop_start()  # Start MQTT loop to keep connection active

# --- Function to send MQTT message ---
def send_mqtt_message(file_name, file_type="audio"):
    if file_type == "audio":
        topic = MQTT_AUDIO_TOPIC
    elif file_type == "json":
        topic = MQTT_JSON_TOPIC
    else:
        raise ValueError("Invalid file type specified.")

    message = f"New {file_type} file uploaded: {file_name}"
    result = mqtt_client.publish(topic, message)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"Sent MQTT message: {message}")
    else:
        print(f"Failed to send message: {message}")

# --- Function to upload a file ---
def upload_file(file_path, file_type="audio"):
    file = os.path.basename(file_path)
    object_name = f"{file_type}/{int(time.time())}_{file}"

    # Define content type based on file type
    if file_type == "audio":
        content_type = "audio/wav" if file.endswith(".wav") else "audio/mpeg"
    elif file_type == "json":
        content_type = "application/json"
    else:
        raise ValueError("Invalid file type specified.")

    try:
        # Upload the file to MinIO
        minio_client.fput_object(BUCKET_NAME, object_name, file_path, content_type=content_type)
        print(f"File uploaded: {object_name}")

        # Notify via MQTT
        send_mqtt_message(object_name, file_type)

        # After uploading, delete the file from the local folder
        os.remove(file_path)
        print(f"File {file} removed from the local folder.")
        return True
    except S3Error as e:
        print(f"Error uploading {file}: {e}")
        return False

# --- Simulation loop ---
def run_simulation():
    empty_checks = 0  # Tracks the number of consecutive failed checks

    while True:
        # Get all valid files from the audio and json directories
        audio_files = [f for f in os.listdir(LOCAL_AUDIO_DIR) if is_valid_audio_format(f)]
        json_files = [f for f in os.listdir(LOCAL_JSON_DIR) if is_valid_json_format(f)]

        # Upload audio files if there are any
        if audio_files:
            empty_checks = 0  # Reset empty counter
            print(f"Found {len(audio_files)} audio file(s). Uploading...")
            for file in audio_files:
                file_path = os.path.join(LOCAL_AUDIO_DIR, file)
                upload_file(file_path, file_type="audio")  # Upload the audio file

        # Upload JSON files if there are any
        if json_files:
            empty_checks = 0  # Reset empty counter
            print(f"Found {len(json_files)} JSON file(s). Uploading...")
            for file in json_files:
                file_path = os.path.join(LOCAL_JSON_DIR, file)
                upload_file(file_path, file_type="json")  # Upload the json file

        # Sleep after checking both directories
        if audio_files or json_files:
            print("All files uploaded. Sleeping for 5 minutes...")
            time.sleep(300)  # Wait 5 minutes before checking again
        else:
            empty_checks += 1
            print(f"No valid files found (check {empty_checks}/6). Sleeping 10 minutes...")
            if empty_checks >= 2:
                print("No valid files added for 1 hour. Stopping the script.")
                break
            time.sleep(600)  # Wait 10 minutes before checking again

if __name__ == "__main__":
    run_simulation()
