from typing import Optional

class DummyMQTTClient:
    """A lightweight stand‑in for a real MQTT client.

    This class mimics the interface of paho.mqtt.client.Client but
    doesn't actually send any data.  It prints a debug message when
    messages are 'published'.  Replace this with
    `import paho.mqtt.client as mqtt` and use `mqtt.Client()` in your
    production environment.
    """

    def __init__(self, host: str, port: int, username: Optional[str] = None,
                 password: Optional[str] = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        # In a real implementation you would establish the connection here.
        print(f"[DummyMQTTClient] Initialized for {host}:{port}")

    def publish(self, topic: str, payload: str, qos: int = 0):
        """Pretend to publish a message to MQTT."""
        # Replace this print with the real publish call:
        # self.client.publish(topic, payload, qos=qos)
        print(f"[MQTT] Topic: {topic} Payload: {payload}")

    def disconnect(self):
        # In a real client you'd close the connection here
        print("[DummyMQTTClient] Disconnecting")


class DummyKafkaProducer:
    """A lightweight stand‑in for a real Kafka producer.

    This class mimics the interface of confluent_kafka.Producer but
    simply prints messages instead of sending them.  Replace this
    implementation with `from confluent_kafka import Producer` and
    construct the Producer with appropriate configuration.
    """

    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        print(f"[DummyKafkaProducer] Initialized for {bootstrap_servers}")

    def produce(self, topic: str, key: Optional[str], value: bytes):
        # In a real producer you'd call producer.produce(topic, key=key, value=value)
        print(f"[Kafka] Topic: {topic} Key: {key} Value: {value.decode('utf-8')}")

    def flush(self):
        # In a real producer you'd wait for all messages to be delivered
        print("[DummyKafkaProducer] Flushing messages")

