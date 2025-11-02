# Image Linker — Run Instructions

## 1. Run the entire project
```bash
docker compose up -d --build
```

## 2. Start the simulator device
Navigate to the simulator directory:
```bash
cd AgCloud/simulator/drone
docker compose up -d --build
```

## 3. Start the Flink linking service
Navigate to the service directory:
```bash
cd AgCloud/services/image-linker
docker compose up -d --build
```

## 4. View metadata messages produced by the simulator
```bash
docker exec -it kafka /opt/bitnami/kafka/bin/kafka-console-consumer.sh   --bootstrap-server kafka:9092   --topic dev-aerial-images-keys   --from-beginning
```

## 5. Listen for messages after successful linking
```bash
docker exec -it kafka /opt/bitnami/kafka/bin/kafka-console-consumer.sh   --bootstrap-server kafka:9092   --topic image.new.aerial.connections
```

## 6. Simulate MinIO bucket notifications
From PowerShell, run:
```powershell
.\send-matching-minio.ps1 -Count 5
```

## 7. Example of expected linked message
After successful matching, a message like this should appear:
```json
{
  "file_name": "drone-01_20251029t093413z.jpg",
  "key": "imagery/air/2025-10-29/123/drone-01_20251029T093413Z.jpg",
  "linked_time": "2025-10-29T09:34:23Z"
}
```
