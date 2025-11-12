import json, uuid, argparse, datetime
from kafka import KafkaProducer

# --------- CLI ---------
p = argparse.ArgumentParser(description="Send alert to Kafka")
p.add_argument("--bootstrap", default="localhost:9092")
p.add_argument("--topic", default="alerts")
p.add_argument("--alert-type", required=True)
p.add_argument("--device-id", required=True)
p.add_argument("--started-at", default=None, help="ISO8601; default=now UTC")
p.add_argument("--lat", type=float, default=None)
p.add_argument("--lon", type=float, default=None)
p.add_argument("--image-url", default=None)
p.add_argument("--severity", type=int, default=3)
p.add_argument("--area", default="north_field")
args = p.parse_args()

# --------- Build payload ---------
# NOTE: Comments are NOT sent; kept here for clarity
payload = {
    # --- Required fields ---
    "alert_id": str(uuid.uuid4()),
    "alert_type": args.alert_type,   # e.g. "fence_hole" or "smoke_detected"
    "device_id": args.device_id,     # e.g. "camera-01"
    "started_at": (
        args.started_at
        if args.started_at
        else datetime.datetime.now(datetime.timezone.utc).isoformat()
    ),
    # --- Optional fields ---
    "confidence": None,              # fill by your detector if available
    "severity": args.severity,
    "area": args.area,
    "lat": args.lat,
    "lon": args.lon,
    "image_url": args.image_url,
    "meta": {},                      # you can enrich with bucket/key, etc.
}

# Remove None fields to keep payload clean
payload = {k: v for k, v in payload.items() if v is not None}

# --------- Send ---------
producer = KafkaProducer(
    bootstrap_servers=args.bootstrap,
    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    linger_ms=50,
    retries=5,
)
fut = producer.send(args.topic, payload)
rec = fut.get(timeout=10)
producer.flush()
print(f"OK: topic={args.topic} partition={rec.partition} offset={rec.offset}")
print(json.dumps(payload, ensure_ascii=False))
