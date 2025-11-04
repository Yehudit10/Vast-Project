from minio import Minio
from minio.error import S3Error
import os
import time

# Reading from ENV
endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
access_key = os.getenv("MINIO_ROOT_USER", "minioadmin")
secret_key = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin123")
secure = os.getenv("MINIO_SECURE", "0") == "1"

# Initialize MinIO client
client = Minio(
    endpoint,
    access_key=access_key,
    secret_key=secret_key,
    secure=secure
)
# Waiting for MinIO be ready
for i in range(20):
    try:
        client.list_buckets()
        print("✅ MinIO is ready.")
        break
    except Exception:
        print("⏳ Waiting for MinIO to be ready...")
        time.sleep(1)
else:
    raise Exception("MinIO not ready after waiting")

# Creating the buckets
for bucket in ["imagery", "sound"]:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        print(f"✅ Created bucket: {bucket}")
    else:
        print(f"ℹ️ Bucket already exists: {bucket}")
