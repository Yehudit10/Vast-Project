# -*- coding: utf-8 -*-
"""
Flink 1.18 PyFlink — HTTP dispatcher (Kafka -> HTTP /infer_json)
- DataStream API: KafkaSource / KafkaSink
- WatermarkStrategy from pyflink.common (compatible with 1.18)
- Splits successful requests to inference.dispatched.<team> and errors to DLQ
"""

import os
import json
import uuid
import asyncio
import argparse
from typing import Any, Dict

import aiohttp

# PyFlink core
from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.datastream.functions import MapFunction, RuntimeContext

# WatermarkStrategy/Types – in Flink 1.18 imported from pyflink.common
from pyflink.common import WatermarkStrategy, Types
from pyflink.common.serialization import SimpleStringSchema

# Kafka connectors
from pyflink.datastream.connectors.kafka import (
    KafkaSource,
    KafkaSink,
    KafkaOffsetsInitializer,
    KafkaRecordSerializationSchema,
)

# -----------------------------
# Args & Config
# -----------------------------
def parse_args():
    p = argparse.ArgumentParser(description="HTTP dispatcher for imagery events")
    p.add_argument("--bootstrap", default=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"))
    p.add_argument("--input-topic", default=os.getenv("INPUT_TOPIC", "imagery.new.fruit"))
    p.add_argument("--team", default=os.getenv("TEAM", "fruit"))
    p.add_argument("--http-url",
                   default=os.getenv("HTTP_URL", "http://fruit-inference-http:8000/infer_json"))
    p.add_argument("--dlq-topic", default=os.getenv("DLQ_TOPIC", "dlq.inference.http"))
    p.add_argument("--group-id", default=os.getenv("GROUP_ID", "http-dispatcher-fruit"))

    # tuning
    p.add_argument("--parallelism", type=int, default=int(os.getenv("PARALLELISM", "2")))
    p.add_argument("--http-connect-timeout", type=float,
                   default=float(os.getenv("HTTP_CONNECT_TIMEOUT", "2.0")))
    p.add_argument("--http-read-timeout", type=float,
                   default=float(os.getenv("HTTP_READ_TIMEOUT", "5.0")))
    p.add_argument("--http-max-retries", type=int,
                   default=int(os.getenv("HTTP_MAX_RETRIES", "5")))
    p.add_argument("--http-retry-backoff-s", type=float,
                   default=float(os.getenv("HTTP_RETRY_BACKOFF_S", "0.5")))
    return p.parse_args()


# -----------------------------
# MapFunction – HTTP POST with retry
# -----------------------------
class HttpMap(MapFunction):
    def __init__(self, http_url: str, connect_timeout: float, read_timeout: float,
                 max_retries: int, retry_backoff_s: float, team: str):
        self.http_url = http_url
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_retries = max_retries
        self.retry_backoff_s = retry_backoff_s
        self.team = team
        self.loop = None
        self.session = None

    def open(self, runtime_context: RuntimeContext):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        timeout = aiohttp.ClientTimeout(total=None,
                                        connect=self.connect_timeout,
                                        sock_read=self.read_timeout)
        self.session = self.loop.run_until_complete(self._make_session(timeout))

    async def _make_session(self, timeout: aiohttp.ClientTimeout) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(timeout=timeout)

    async def _post_once(self, url: str, payload: Dict[str, Any], headers: Dict[str, str]):
        async with self.session.post(url, json=payload, headers=headers) as resp:
            return resp.status, await resp.text()

    async def _post_with_retry(self, url: str, payload: Dict[str, Any], headers: Dict[str, str]):
        attempt = 0
        while True:
            try:
                status, text = await self._post_once(url, payload, headers)
                if 200 <= status < 300:
                    return {"ok": True, "status": status, "body": text}
                # Do not retry most 4xx except 408/429
                if 400 <= status < 500 and status not in (408, 429):
                    return {"ok": False, "status": status, "body": text, "retry": False}
                attempt += 1
                if attempt > self.max_retries:
                    return {"ok": False, "status": status, "body": text, "retry": False}
                await asyncio.sleep(self.retry_backoff_s * attempt)
            except Exception as e:
                attempt += 1
                if attempt > self.max_retries:
                    return {"ok": False, "status": 599, "body": str(e), "retry": False}
                await asyncio.sleep(self.retry_backoff_s * attempt)

    def map(self, s: str) -> str:
        # 1) Parse JSON
        try:
            event = json.loads(s)
        except Exception as e:
            return json.dumps(
                {"ok": False, "status": 422, "body": f"bad json: {e}", "raw": s, "stage": "parse"},
                ensure_ascii=False
            )

        # 2) Generate idempotency key
        event_id = event.get("event_id") or str(uuid.uuid4())

        # 3) Validate fields: must have bucket+key; image_uri not allowed
        if "image_uri" in event:
            return json.dumps(
                {"ok": False, "status": 422,
                 "body": "image_uri not supported; use {bucket,key} only",
                 "event": event, "stage": "validate"},
                ensure_ascii=False
            )

        bucket = event.get("bucket")
        key = event.get("key")
        if not bucket or not key:
            return json.dumps(
                {"ok": False, "status": 422,
                 "body": "missing required fields: bucket and key",
                 "event": event, "stage": "validate"},
                ensure_ascii=False
            )

        # 4) Prepare headers and payload: send only bucket/key to the inference service
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": event_id,
            "X-Correlation-ID": event_id,
        }
        payload = {"bucket": bucket, "key": key}

        # 5) Execute HTTP POST with retry logic
        res = self.loop.run_until_complete(self._post_with_retry(self.http_url, payload, headers))

        # 6) Wrap output into a consistent JSON response
        out = {
            "event_id": event_id,
            "team": self.team,
            "http_url": self.http_url,
            **res,
            "event": event
        }
        return json.dumps(out, ensure_ascii=False)

    def close(self):
        try:
            if self.session is not None:
                self.loop.run_until_complete(self.session.close())
        finally:
            if self.loop is not None:
                self.loop.close()


# -----------------------------
# Flink Topology
# -----------------------------
def build_env(parallelism: int) -> StreamExecutionEnvironment:
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.set_parallelism(parallelism)
    return env


def build_source(env: StreamExecutionEnvironment, bootstrap: str, group_id: str, topic: str):
    src = (
        KafkaSource.builder()
        .set_bootstrap_servers(bootstrap)
        .set_group_id(group_id)
        .set_topics(topic)
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    return env.from_source(src, WatermarkStrategy.no_watermarks(), "kafka-source")


def build_sink(bootstrap: str, topic: str):
    return (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(topic)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )


def main():
    args = parse_args()

    env = build_env(args.parallelism)
    ds = build_source(env, args.bootstrap, args.group_id, args.input_topic)

    mapper = HttpMap(
        http_url=args.http_url,
        connect_timeout=args.http_connect_timeout,
        read_timeout=args.http_read_timeout,
        max_retries=args.http_max_retries,
        retry_backoff_s=args.http_retry_backoff_s,
        team=args.team,
    )
    dispatched = ds.map(mapper, output_type=Types.STRING())

    def _is_ok(s: str) -> bool:
        try:
            return bool(json.loads(s).get("ok"))
        except Exception:
            return False

    ok_stream = dispatched.filter(_is_ok)
    bad_stream = dispatched.filter(lambda s: not _is_ok(s))

    ok_topic = f"inference.dispatched.{args.team}"
    ok_stream.sink_to(build_sink(args.bootstrap, ok_topic))
    bad_stream.sink_to(build_sink(args.bootstrap, args.dlq_topic))

    env.execute(f"http-dispatcher-{args.team}")


if __name__ == "__main__":
    main()
