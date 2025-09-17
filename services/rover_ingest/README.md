# rover_ingest
## Local run
set MINIO_ENDPOINT=localhost:9000
set MINIO_BUCKET=rover-images
set MINIO_ACCESS_KEY=minioadmin
set MINIO_SECRET_KEY=minioadmin
set PG_DSN="dbname=missions_db user=missions_user host=localhost password=pg123"
python -m services.rover_ingest.app
