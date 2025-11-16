"""
Flink Python DataStream job:
- Kafka source (JSON notifications)
- Per-record HTTP classification via pooled Session (processor.process_json_line)
- Optional Kafka sink; if SINK_TOPIC is empty -> print to stdout
"""

from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import (
    KafkaSource, KafkaSink, KafkaRecordSerializationSchema, DeliveryGuarantee
)
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.datastream.checkpointing_mode import CheckpointingMode
from pyflink.common import Types
from processor import process_json_line

from config import (
    KAFKA_BROKERS,
    SOURCE_TOPIC,
    SINK_TOPIC,
    GROUP_ID,
    KAFKA_START,
    DEFAULT_PARALLELISM,
    CHECKPOINT_MS,
    DELIVERY_GUARANTEE,
    TRANSACTION_TIMEOUT_MS,
)

def main():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(DEFAULT_PARALLELISM)
    env.enable_checkpointing(CHECKPOINT_MS, CheckpointingMode.EXACTLY_ONCE)

    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(KAFKA_BROKERS)
        .set_topics(SOURCE_TOPIC)
        .set_group_id(GROUP_ID)
        .set_property("auto.offset.reset", KAFKA_START)
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    stream = env.from_source(
        source,
        WatermarkStrategy.no_watermarks(),
        f"source-{SOURCE_TOPIC}",
    )

    mapped = stream.map(process_json_line, output_type=Types.STRING())
    filtered = mapped.filter(lambda s: bool(s and s.strip()))

    # Always print for quick debugging
    filtered.name("stdout-preview").print()

    # Optional Kafka sink
    if SINK_TOPIC:
        guarantee = (
            DeliveryGuarantee.AT_LEAST_ONCE
            if DELIVERY_GUARANTEE.upper() == "AT_LEAST_ONCE"
            else DeliveryGuarantee.NONE
        )
        sink = (
            KafkaSink.builder()
            .set_bootstrap_servers(KAFKA_BROKERS)
            .set_record_serializer(
                KafkaRecordSerializationSchema.builder()
                .set_topic(SINK_TOPIC)
                .set_value_serialization_schema(SimpleStringSchema())
                .build()
            )
            .set_delivery_guarantee(guarantee)
            .set_property("transaction.timeout.ms", TRANSACTION_TIMEOUT_MS)
            .build()
        )
        filtered.sink_to(sink).name(f"sink-{SINK_TOPIC}")

    env.execute("flink-http-classifier")


if __name__ == "__main__":
    main()
