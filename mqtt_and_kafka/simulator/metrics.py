from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Metrics:
    """Counters and timing samples for Kafka and MQTT."""
    sent_kafka: int = 0
    acked_kafka: int = 0
    lost_kafka: int = 0
    sent_mqtt: int = 0
    acked_mqtt: int = 0
    lost_mqtt: int = 0

    kafka_latencies: List[float] = field(default_factory=list)
    mqtt_latencies: List[float] = field(default_factory=list)
    inter_arrivals: List[float] = field(default_factory=list)

    def loss_rates(self) -> Dict[str, float]:
        """Loss rate (% per transport)."""
        lk = (self.lost_kafka / max(self.sent_kafka, 1)) * 100.0
        lm = (self.lost_mqtt / max(self.sent_mqtt, 1)) * 100.0
        return {"kafka_loss_pct": lk, "mqtt_loss_pct": lm}
