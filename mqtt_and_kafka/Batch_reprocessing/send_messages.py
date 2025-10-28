from confluent_kafka import Producer
import json
import time
import random

producer = Producer({'bootstrap.servers': 'kafka:9092'})

try:
    while True:
        msg = {
            "mic_id": f"mic-{random.randint(1,3)}",
            "window_start": "2025-09-29T00:00:00Z",
            "window_end": "2025-09-29T00:05:00Z",
            "metrics": {
                "avg_volume_db": round(random.uniform(-30, 0), 1),
                "max_volume_db": round(random.uniform(-10, 0), 1),
                "anomaly_count": random.randint(0, 5)
            }
        }
        producer.produce('summaries.5m', json.dumps(msg).encode('utf-8'))
        producer.flush()
        print("Sent message:", msg)
        time.sleep(1)  

except KeyboardInterrupt:
    print("Stopped sending messages.")
