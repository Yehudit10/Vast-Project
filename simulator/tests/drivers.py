from __future__ import annotations

from collections import deque
from typing import Any, Callable, Deque, Optional, Tuple


class DummyMQTTClient:
    """
    Minimal MQTT dummy used to test control/metrics logic without a live broker.
    """
    MQTT_ERR_SUCCESS = 0

    def __init__(self, client_id: str):
        self.client_id = client_id
        self.connected = False
        self._mid = 0
        self._userdata = None
        self.on_publish: Optional[Callable[[Any, Any, int], None]] = None
        self._pending_acks: Deque[int] = deque() 
        
    def username_pw_set(self, username=None, password=None) -> None: ...
    def tls_set(self, *_, **__) -> None: ...
    def user_data_set(self, userdata) -> None: self._userdata = userdata
    def loop_start(self) -> None: ...
    def loop_stop(self) -> None: ...

    def connect(self, host: str, port: int = 1883, keepalive: int = 60) -> int:
        self.connected = True
        return self.MQTT_ERR_SUCCESS

    def publish(self, topic: str, payload: Optional[str] = None, qos: int = 0, retain: bool = False) -> Tuple[int, int]:
        """
        Simulate synchronous PUBACK by immediately invoking on_publish.
        Returns (rc, mid) like old paho signatures for simplicity.
        """
        if not self.connected:
            raise RuntimeError("MQTT not connected")
        self._mid += 1
        mid = self._mid
        self._pending_acks.append(mid)
        return self.MQTT_ERR_SUCCESS, mid

    def poll(self) -> int: 
        """
        Emit all pending on_publish callbacks; returns number of ACKs fired.
        """
        fired = 0
        while self._pending_acks:
            mid = self._pending_acks.popleft()
            if callable(self.on_publish):
                self.on_publish(self, self._userdata, mid)
            fired += 1
        return fired
    
    def disconnect(self) -> None:
        self.connected = False
        self._pending_acks.clear()


class DummyKafkaProducer:
    """
    Minimal Kafka dummy that queues messages and 'delivers' them on poll().
    """

    class _Msg:
        def __init__(self, topic, key, value, headers=None):
            self._topic, self._key, self._value = topic, key, value
            self._headers = headers or []
        def topic(self): return self._topic
        def key(self):   return self._key
        def value(self): return self._value
        def headers(self): return self._headers

    def __init__(self, conf=None):
        self._q: Deque = deque()
        self._closed = False

    def produce(self, topic, key=None, value=None, callback=None, **kwargs):
        if self._closed:
            raise RuntimeError("Producer closed")
        headers = kwargs.get("headers")
        self._q.append((topic, key, value, headers, callback))

    def poll(self, timeout: float = 0) -> int:
        """
        Deliver all queued messages immediately for simplicity.
        """
        delivered = 0
        while self._q:
            topic, key, value, headers, cb = self._q.popleft()
            if cb:
                cb(None, DummyKafkaProducer._Msg(topic, key, value, headers))  # err=None => success
            delivered += 1
        return delivered

    def flush(self, timeout: Optional[float] = None) -> None:
        self.poll(0)

    def close(self) -> None:
        self.flush()
        self._closed = True
