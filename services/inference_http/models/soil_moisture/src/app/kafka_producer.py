import json
import logging
from confluent_kafka import Producer, KafkaError
from .metrics import METRICS

logger = logging.getLogger("soil_api")

class ControlProducer:
    def __init__(self, brokers: str, topic: str, dlt: str):
        self.topic = topic
        self.dlt = dlt
        self.producer = Producer({"bootstrap.servers": brokers})

    def publish(self, payload: dict) -> None:
        try:
            self.producer.produce(
                self.topic,
                value=json.dumps(payload).encode("utf-8"),
                on_delivery=self._delivery_report
            )
            self.producer.flush(2)
            METRICS["alerts_sent_total"].labels(decision=payload.get("command", "unknown")).inc()
        except Exception as e:
            logger.warning("Kafka publish failed: %s", e)
            METRICS["kafka_publish_errors_total"].labels(reason=type(e).__name__).inc()
            # try send to DLT
            try:
                dlt_payload = dict(payload)
                dlt_payload["error"] = str(e)
                self.producer.produce(self.dlt, value=json.dumps(dlt_payload).encode("utf-8"))
                self.producer.flush(2)
            except Exception as e2:
                logger.error("DLT publish failed: %s", e2)

    def _delivery_report(self, err, msg):
        if err is not None:
            logger.warning("Delivery failed for record %s: %s", msg.key(), err)
        else:
            logger.debug("Record delivered to %s [%d] @ %d", msg.topic(), msg.partition(), msg.offset())
