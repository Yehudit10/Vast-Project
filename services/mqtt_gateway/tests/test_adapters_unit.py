# services/mqtt_gateway/tests/test_adapters_unit.py
from __future__ import annotations
from unittest.mock import Mock, patch
import types

def test_minio_store_put_object_calls_boto3_correctly():
    # Fake boto3 + botocore modules
    fake_s3_client = Mock()
    fake_s3_client.put_object = Mock()
    fake_s3_client.upload_fileobj = Mock()

    def fake_import(name):
        if name == "boto3":
            # expose client() that returns our fake client
            m = types.SimpleNamespace(client=lambda *a, **k: fake_s3_client)
            return m
        if name == "botocore.config":
            class _Cfg:
                def __init__(self, **kwargs): pass
            return types.SimpleNamespace(Config=_Cfg)
        if name == "boto3.s3.transfer":
            class _Tx:
                def __init__(self, multipart_threshold, multipart_chunksize, max_concurrency, use_threads):
                    self.multipart_threshold = multipart_threshold
            return types.SimpleNamespace(TransferConfig=_Tx)
        raise ImportError(name)

    with patch("services.mqtt_gateway.adapters.minio_store.importlib.import_module", side_effect=fake_import):
        from services.mqtt_gateway.adapters.minio_store import Boto3ImageStore
        store = Boto3ImageStore(endpoint_url="http://minio:9000", access_key="a", secret_key="s")
        sha, size = store.put_object("bkt", "key", b"1234", "image/jpeg")
        # For small payload (4 bytes) → put_object path
        fake_s3_client.put_object.assert_called_once()
        assert sha and size == 4

def test_kafka_producer_json_serialization():
    fake_prod = Mock()

    def fake_import(name):
        if name == "confluent_kafka":
            return types.SimpleNamespace(Producer=lambda conf: fake_prod)
        raise ImportError(name)

    with patch("services.mqtt_gateway.adapters.kafka_producer.importlib.import_module", side_effect=fake_import):
        from services.mqtt_gateway.adapters.kafka_producer import ConfluentEventBusProducer
        k = ConfluentEventBusProducer("kafka:9092")
        k.send("t", "k1", {"a": 1})
        fake_prod.produce.assert_called_once()
        args, kwargs = fake_prod.produce.call_args
        assert kwargs["topic"] == "t"
        assert kwargs["key"] == "k1"
        assert isinstance(kwargs["value"], (bytes, bytearray))
