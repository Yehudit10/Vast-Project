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
