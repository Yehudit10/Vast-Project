# Sound Classifier Service

A machine learning service for sound classification using PyTorch, running as a FastAPI application.

## Overview

This service provides sound classification capabilities using a CNN14 model architecture. It runs as a containerized service that integrates with Kafka for event streaming and PostgreSQL for data persistence.

## Requirements

- Docker and Docker Compose
- At least 2GB RAM available for the service
- Access to required model checkpoints (CNN14 model)

## Environment Variables

The service requires the following environment variables to be set in `src/classification/.env`:

- Database configuration (PostgreSQL)
- Kafka configuration
- Model configuration

## Quick Start

1. Ensure you have the required model checkpoint file:
   - Default location: `/app/classification/models/panns_data/Cnn14_mAP=0.431.pth`
   - Or specify custom location via `CHECKPOINT_URL` and `CHECKPOINT_PATH` environment variables

2. Start the service using Docker Compose:
   ```bash
   docker-compose up classifier
   ```

The service will be available at `http://localhost:8088`

## Dependencies

The service depends on:
- PostgreSQL database
- Kafka message broker
- Desktop app service
- MinIO (for storage)

## Technical Details

- Base image: Python 3.12 slim
- Key Libraries:
  - PyTorch (CPU version)
  - FastAPI/Uvicorn
  - libsndfile and ffmpeg for audio processing
  - Kafka and PostgreSQL clients

## API Endpoints

The service exposes its API on port 8088. Detailed API documentation is available at:
- Swagger UI: `http://localhost:8088/docs`
- ReDoc: `http://localhost:8088/redoc`

## Docker Configuration

The service is configured to:
- Automatically restart on failure
- Use custom CA certificates if needed
- Run with unbuffered Python output for better logging
- Optimize for CPU-based inference

## Development

To develop or modify the service:

1. Clone the repository
2. Modify the source code in `src/classification/`
3. Build and run the container:
   ```bash
   docker-compose build classifier
   docker-compose up classifier
   ```

## Troubleshooting

Common issues:
1. Missing model checkpoint - Ensure the model file is available or the download URL is correct
2. Memory issues - Check container resource allocation
3. Connection issues - Verify PostgreSQL and Kafka connectivity
