# Sound Classifier Service

Service that classifies audio files using CNN14 model. It:
1. Receives S3 object location (bucket+key)
2. Classifies the sound
3. Stores result in PostgreSQL (optional)
4. Sends alert to Kafka topic if specific sounds detected (optional)

## Quick Start
```bash
docker-compose up classifier
```
Service available at `http://localhost:8088`

## API Usage
```json
POST /classify
{
    "s3_bucket": "your-bucket",
    "s3_key": "path/to/audio.wav"
}
```

## Supported Audio Formats
- WAV, MP3, FLAC, OGG
- M4A, AAC, WMA, OPUS

## Required Environment Variables
Create `.env` file with:
```
# MinIO Connection
MINIO_ENDPOINT=
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
MINIO_SECURE=

# Model Configuration
MODEL_PATH=
DEVICE=cpu/cuda

# Optional Features
DB_URL=              # PostgreSQL connection for logging
KAFKA_BROKERS=       # For alerts
ALERTS_TOPIC=        # Kafka topic for alerts
```

## System Requirements

- Docker and Docker Compose
- Storage space for audio processing
- MinIO instance for audio file storage

## API Documentation

Browse the complete API documentation at:
- http://localhost:8088/docs

## Support

For issues or questions, please create an issue in our repository.
