from minio import Minio
import os

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9001")
ACCESS_KEY = os.getenv("ACCESS_KEY", "minioadmin")
SECRET_KEY = os.getenv("SECRET_KEY", "minioadmin123")
BUCKET_NAME = os.getenv("BUCKET_NAME", "sound")

client = Minio(
    MINIO_ENDPOINT,
    access_key=ACCESS_KEY,
    secret_key=SECRET_KEY,
    secure=False,
)

if not client.bucket_exists(BUCKET_NAME):
    client.make_bucket(BUCKET_NAME)
