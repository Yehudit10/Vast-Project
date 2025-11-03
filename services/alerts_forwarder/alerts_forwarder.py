import os, json, requests
from pyflink.common import Types
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.watermark_strategy import WatermarkStrategy

ALERTMANAGER_SERVICE_URL = "http://alertmanager_service:8090/alerts"
KAFKA_BROKERS = "kafka:9092"
TOPIC = "alerts"

def send_to_alertmanager(alert_json: str):
    try:
        data = json.loads(alert_json)
        resp = requests.post(ALERTMANAGER_SERVICE_URL, json=data, timeout=5)
        if resp.status_code == 200:
            print(f"✅ Sent alert {data.get('alert_id')}", flush=True)
        else:
            print(f"❌ {resp.status_code}: {resp.text}", flush=True)
    except Exception as e:
        print(f"Failed to send alert: {e}", flush=True)

def main():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(int(os.getenv("FLINK_PARALLELISM", "1")))

    print(f"[FLINK] Listening on topic: {TOPIC}", flush=True)

    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(KAFKA_BROKERS)
        .set_topics(TOPIC)
        .set_group_id("flink-alerts-to-alertmanager")
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "Kafka Alerts Source")

    # ✅ Must have a terminal operator
    stream.map(
        lambda raw: (send_to_alertmanager(raw) or True),
        output_type=Types.BOOLEAN()
    ).print()

    env.execute("Flink Alerts → AlertManager Forwarder")

if __name__ == "__main__":
    main()



