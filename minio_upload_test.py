# minio_upload_test.py
# Simple MinIO upload sanity-check using env vars.
# It creates the bucket if missing, uploads a local image, and prints the object key and a presigned URL.

import os
from datetime import datetime, timezone
from minio import Minio
from minio.error import S3Error

def main():
    # Read connection from environment (fallbacks provided for local dev)
    endpoint   = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
    bucket     = os.getenv("MINIO_BUCKET", "rover-images")
    secure     = os.getenv("MINIO_SECURE", "false").lower() == "true"

    # Set your local image path and destination key in the bucket
    local_image = os.getenv("LOCAL_IMAGE", r"C:\Users\sara\Documents\bootk\AgCloud\data\fence_holes\test\images\ChatGPT Image Sep 30, 20252, 08_07_34 PM.png")
    object_key  = os.getenv("MINIO_OBJECT_KEY", "images/camera-01/2025/11/04/1762242644028/ChatGPT Image Sep 30, 20252, 08_07_34 PM.png")

    print(f"[INFO] Connecting MinIO  endpoint={endpoint!r}  secure={secure}")
    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    try:
        if not client.bucket_exists(bucket):
            print(f"[INFO] Bucket {bucket!r} not found, creating...")
            client.make_bucket(bucket)
        else:
            print(f"[INFO] Bucket {bucket!r} exists.")

        captured_at = datetime.now(timezone.utc).isoformat()
        metadata = {"captured_at": captured_at}  # simple metadata

        # Upload file (content-type best effort)
        print(f"[INFO] Uploading {local_image!r} -> s3://{bucket}/{object_key}")
        client.fput_object(
            bucket_name=bucket,
            object_name=object_key,
            file_path=local_image,
            metadata=metadata,
            content_type="image/jpeg" if local_image.lower().endswith((".jpg", ".jpeg")) else "image/png",
        )

        # Optional: presigned GET URL (valid 1 day)
        url = client.get_presigned_url("GET", bucket, object_key)
        print("[OK] uploaded:", bucket, object_key)
        print("[OK] captured_at:", captured_at)
        print("[OK] presigned_url:", url)

    except S3Error as e:
        print("[ERROR] MinIO S3Error:", e)
        raise
    except Exception as e:
        print("[ERROR] General failure:", e)
        raise

if __name__ == "__main__":
    main()
