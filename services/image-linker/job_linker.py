#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Flink job: real-time matcher between metadata and MinIO events
--------------------------------------------------------------
- Matches file_name between two Kafka topics
- Order-independent (works even if MinIO arrives before metadata)
- Clears state immediately after a successful match
- 5-minute TTL cleanup for unmatched (orphan) entries
- Exactly-once Kafka delivery
"""

import os
import json
import time
import pathlib
import yaml
from pyflink.common import Types, WatermarkStrategy
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import (
    KafkaSource, KafkaSink, KafkaRecordSerializationSchema, DeliveryGuarantee
)
from pyflink.datastream.functions import CoProcessFunction, RuntimeContext
from pyflink.datastream.state import ValueStateDescriptor
from pyflink.datastream.checkpointing_mode import CheckpointingMode
from pyflink.common.serialization import SimpleStringSchema


# ---------- Configuration ----------
CONFIG_PATH = os.getenv("CONFIG_PATH", "/opt/app/config/topics.yaml")
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka:9092")
TTL_MS = 5 * 60 * 1000  # 5 minutes TTL for orphan cleanup


# ---------- Helper Functions ----------
def normalize_name(name: str) -> str:
    """Normalize file name for consistent matching."""
    if not name:
        return ""
    return pathlib.Path(name.strip().replace('"', "")).name.lower()


def try_parse_json(raw: str):
    """Safely parse a JSON string."""
    try:
        return json.loads(raw)
    except Exception:
        return None


def extract_file_name(raw: str) -> str:
    """Extract normalized file_name from metadata or MinIO message."""
    data = try_parse_json(raw)
    if not data:
        return ""
    if "file_name" in data:
        return normalize_name(data["file_name"])
    if "Key" in data:
        return normalize_name(pathlib.Path(data["Key"]).name)
    records = data.get("Records") or []
    if records and "s3" in records[0]:
        key = records[0]["s3"]["object"]["key"]
        return normalize_name(pathlib.Path(key).name)
    return ""


# ---------- Matcher Class ----------
class Matcher(CoProcessFunction):
    """CoProcessFunction that joins two Kafka streams by file_name."""

    def __init__(self):
        self.meta_state = None
        self.minio_state = None
        self.cleanup_ts_state = None

    def open(self, ctx: RuntimeContext):
        self.meta_state = ctx.get_state(ValueStateDescriptor("meta_state", Types.STRING()))
        self.minio_state = ctx.get_state(ValueStateDescriptor("minio_state", Types.STRING()))
        self.cleanup_ts_state = ctx.get_state(ValueStateDescriptor("cleanup_ts_state", Types.LONG()))

    def process_element1(self, value, ctx):
        """Handle metadata messages."""
        img = extract_file_name(value)
        self._register_cleanup_timer(ctx)
        self.meta_state.update(value)
        minio_val = self.minio_state.value()
        if minio_val:
            yield self._emit_and_clear(img, value, minio_val)

    def process_element2(self, value, ctx):
        """Handle MinIO messages."""
        img = extract_file_name(value)
        self._register_cleanup_timer(ctx)
        self.minio_state.update(value)
        meta_val = self.meta_state.value()
        if meta_val:
            yield self._emit_and_clear(img, meta_val, value)

    def _emit_and_clear(self, file_name, meta_raw, minio_raw):
        """Emit a short match result and clear both states immediately."""
        minio_data = try_parse_json(minio_raw) or {}
        key = minio_data.get("Key") or minio_data.get("key")

        print(f"[MATCH] {file_name} -> {key}")

        # Clear both states after successful match
        self.meta_state.clear()
        self.minio_state.clear()
        self.cleanup_ts_state.clear()

        # Emit minimal message
        result = {
            "file_name": file_name,
            "key": key,
            "linked_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        return json.dumps(result)

    def _register_cleanup_timer(self, ctx):
        """Register cleanup timer for orphan entries."""
        now = ctx.timer_service().current_processing_time()
        scheduled = self.cleanup_ts_state.value()
        if scheduled is None or now + TTL_MS > scheduled:
            ts = now + TTL_MS
            ctx.timer_service().register_processing_time_timer(ts)
            self.cleanup_ts_state.update(ts)

    def on_timer(self, timestamp, ctx):
        """Automatically clear unmatched states after TTL."""
        print(f"[CLEANUP] Timer fired at {time.strftime('%H:%M:%S', time.gmtime(timestamp / 1000))}")
        self.meta_state.clear()
        self.minio_state.clear()
        self.cleanup_ts_state.clear()
        print("[CLEANUP] Cleared stale state after 5 minutes")
        yield from []  # fix: must return iterable (even empty)


# ---------- Main Function ----------
def main():
    # Load configuration file
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    teams = cfg.get("teams", {})
    if not teams:
        raise RuntimeError(f"No teams found in {CONFIG_PATH}")

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    env.enable_checkpointing(10000, CheckpointingMode.EXACTLY_ONCE)

    for team, info in teams.items():
        meta_t = info["metadata_topic"]
        minio_t = info["minio_topic"]
        out_t = info["output_topic"]

        print(f"[FLINK] {meta_t} + {minio_t} -> {out_t}")

        # Create Kafka sources
        meta_src = (
            KafkaSource.builder()
            .set_bootstrap_servers(KAFKA_BROKERS)
            .set_topics(meta_t)
            .set_group_id(f"flink-{team}-meta")
            .set_property("auto.offset.reset", "latest")
            .set_value_only_deserializer(SimpleStringSchema())
            .build()
        )

        minio_src = (
            KafkaSource.builder()
            .set_bootstrap_servers(KAFKA_BROKERS)
            .set_topics(minio_t)
            .set_group_id(f"flink-{team}-minio")
            .set_property("auto.offset.reset", "latest")
            .set_value_only_deserializer(SimpleStringSchema())
            .build()
        )

        meta_stream = env.from_source(meta_src, WatermarkStrategy.no_watermarks(), f"{team}-meta")
        minio_stream = env.from_source(minio_src, WatermarkStrategy.no_watermarks(), f"{team}-minio")

        # Key both streams by file_name
        keyed_meta = meta_stream.key_by(extract_file_name, key_type=Types.STRING())
        keyed_minio = minio_stream.key_by(extract_file_name, key_type=Types.STRING())

        # Connect and process both streams
        matched_stream = keyed_meta.connect(keyed_minio).process(Matcher(), output_type=Types.STRING())

        # Define Kafka sink
        sink = (
            KafkaSink.builder()
            .set_bootstrap_servers(KAFKA_BROKERS)
            .set_record_serializer(
                KafkaRecordSerializationSchema.builder()
                .set_topic(out_t)
                .set_value_serialization_schema(SimpleStringSchema())
                .build()
            )
            .set_delivery_guarantee(DeliveryGuarantee.EXACTLY_ONCE)
            .set_transactional_id_prefix(f"{team}-linker-")
            .set_property("transaction.timeout.ms", "600000")
            .build()
        )

        # Write results to sink
        matched_stream.sink_to(sink)

    env.execute("flink-image-linker-realtime")


if __name__ == "__main__":
    main()
