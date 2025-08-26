from collections import deque

class DummyMQTTClient:
    MQTT_ERR_SUCCESS = 0
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.connected = False
        self._mid = 0
        self._userdata = None
        self.on_publish = None  # callable(client, userdata, mid)

    def username_pw_set(self, username=None, password=None): pass
    def tls_set(self, *_, **__): pass
    def user_data_set(self, userdata): self._userdata = userdata
    def loop_start(self): pass
    def loop_stop(self): pass

    def connect(self, host, port=1883, keepalive=60):
        self.connected = True
        return self.MQTT_ERR_SUCCESS

    def publish(self, topic, payload=None, qos=0, retain=False):
        if not self.connected:
            raise RuntimeError("MQTT not connected")
        self._mid += 1
        mid = self._mid
        # simulate immediate ACK
        if callable(self.on_publish):
            self.on_publish(self, self._userdata, mid)
        return self.MQTT_ERR_SUCCESS, mid

    def disconnect(self):
        self.connected = False


class DummyKafkaProducer:
    class _Msg:
        def __init__(self, topic, key, value):
            self._topic, self._key, self._value = topic, key, value
        def topic(self): return self._topic
        def key(self):   return self._key
        def value(self): return self._value

    def __init__(self, conf=None):
        self._q = deque()
        self._closed = False

    def produce(self, topic, key=None, value=None, callback=None, **kwargs):
        if self._closed:
            raise RuntimeError("Producer closed")
        self._q.append((topic, key, value, callback))

    def poll(self, timeout=0):
        delivered = 0
        while self._q:
            topic, key, value, cb = self._q.popleft()
            if cb:
                cb(None, DummyKafkaProducer._Msg(topic, key, value))  # err=None => success
            delivered += 1
        return delivered

    def flush(self, timeout=None):
        self.poll(0)

    def close(self):
        self.flush()
        self._closed = True


import argparse

def positive_float(x: str) -> float:
    try:
        value = float(x)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a number")
    if value <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return value

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay telemetry at a fixed QPS to MQTT/Kafka")
    parser.add_argument("--qps", type=positive_float, required=True,
                   help="Messages per second to send (must be > 0)")
    parser.add_argument("--duration", type=positive_float, required=True,
                   help="Total run time in seconds (must be > 0)")
    parser.add_argument("--out", choices=["mqtt", "kafka", "both"], default="both",
                   help="Where to publish messages: mqtt, kafka of both (default: both)")
    parser.add_argument("--file", required=True, help="Path to .csv or .parquet file with telemetry data")
    parser.add_argument("--mqtt-host", default="localhost", help="MQTT broker hostname (default: localhost)")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument("--mqtt-topic", default="telemetry", help="MQTT topic to publish to (default: telemetry)")
    parser.add_argument("--kafka-brokers", default="localhost:9092",
                   help="Kafka bootstrap servers (default: localhost:9092)")
    parser.add_argument("--kafka-topic", default="telemetry",
                   help="Kafka topic to publish to (default: telemetry)")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    print(f"CLI OK: qps={args.qps}, duration={args.duration}, out={args.out}")


if __name__ == "__main__":
    main()