import argparse
import json
from kafka import KafkaConsumer, errors

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brokers", default="localhost:29092", help="Broker list, e.g. localhost:29092 or kafka:9092")
    parser.add_argument("--topic", default="irrigation.control")
    parser.add_argument("--group", default="debug-consumer")
    parser.add_argument("--from-beginning", action="store_true", help="Read from earliest offset")
    args = parser.parse_args()

    print(f"Connecting to Kafka brokers: {args.brokers}")
    try:
        consumer = KafkaConsumer(
            args.topic,
            bootstrap_servers=args.brokers.split(","),
            group_id=args.group,
            enable_auto_commit=False,
            auto_offset_reset="earliest" if args.from_beginning else "latest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            consumer_timeout_ms=0
        )
        print(f"Listening on topic '{args.topic}' (group={args.group})...")
    except errors.NoBrokersAvailable:
        print("❌ Cannot connect to Kafka. Check host/port and Docker networking.")
        return

    try:
        for message in consumer:
            print("\n--- New message ---")
            print(json.dumps(message.value, indent=2))
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        consumer.close()
        print("Consumer closed.")

if __name__ == "__main__":
    main()
