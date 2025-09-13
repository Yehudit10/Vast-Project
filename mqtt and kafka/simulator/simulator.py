from __future__ import annotations

import argparse
import json
from collections import deque
from statistics import pstdev
import time
from typing import Dict, Optional

import pandas as pd
from confluent_kafka import Producer
import paho.mqtt.client as mqtt

from simulator.metrics import Metrics
from simulator.utils import iterate_records, percentile, fmt_latency, extract_sid_from_headers


class Simulator:
    """Send loop, rate control, and metrics aggregation."""

    def __init__(self, args: argparse.Namespace, df: pd.DataFrame):
        self.args = args
        self.df = df

        # MQTT
        self.mqtt = mqtt.Client(client_id="simulator", protocol=mqtt.MQTTv311)
        self.mqtt.on_publish = self._on_mqtt_publish

        # Kafka
        conf = {
            "bootstrap.servers": args.kafka_bootstrap, 
            "client.id": "simulator",
            "acks": "all",
            "linger.ms": 5,
            "batch.num.messages": 10000,
            "message.timeout.ms": 10000,
            "enable.idempotence": True,
            "delivery.report.only.error": False
        }
        self.kafka = Producer(conf)
        
        # Inflight maps: mid/sid -> send_time
        self.inflight_mqtt: Dict[int, float] = {}
        self.inflight_kafka: Dict[str, float] = {}

        self.metrics = Metrics()

        # Rate / status
        self.window_sec = float(args.window_sec)
        self.status_every = float(args.status_every)

        # Book-keeping
        self._kafka_sid_seq = 0
        self._last_send_time: Optional[float] = None

    # --- Callbacks ---

    def _delivery_report(self, err, msg):
        """Kafka delivery callback."""
        if err is None:
            self.metrics.acked_kafka += 1
            sid = None
            
            try:
                k = msg.key()
                if isinstance(k, (bytes, bytearray)):
                    sid = k.decode()
                elif k is not None:
                    sid = str(k)
            except Exception:
                sid = None

            start_ts = self.inflight_kafka.pop(sid, None) if sid else None
            if start_ts is not None:
                self.metrics.kafka_latencies.append(time.perf_counter() - start_ts)

        else:
            self.metrics.lost_kafka += 1
            try:
                print(f"[kafka-error] topic={msg.topic()} key={msg.key()} reason={err}")
            except Exception:
                print(f"[kafka-error] reason={err}")    

    def _on_mqtt_publish(self, client, userdata, mid):
        """MQTT on_publish: update ack counters and latency."""
        self.metrics.acked_mqtt += 1
        start_ts = self.inflight_mqtt.pop(mid, None)
        if start_ts is not None:
            self.metrics.mqtt_latencies.append(time.perf_counter() - start_ts)

    # --- Core run ---

    def run(self) -> None:
        """Run the send loop, enforce QPS/duration, print status and summary."""
        args = self.args

        # Connect MQTT
        self.mqtt.connect(args.mqtt_host, args.mqtt_port)
        self.mqtt.loop_start()

        # Record iterator (optionally loop)
        records = list(iterate_records(self.df))
        if not records:
            raise ValueError("Input file contains no records")
        if args.loop:
            from itertools import cycle
            iterator = cycle(records)  # WHY: Sustain long tests with a short sample.
        else:
            iterator = iter(records)

        # Rate control
        interval = 1.0 / args.qps
        send_window = deque()

        start = time.perf_counter()
        end_time = start + args.duration
        last_status_t = start
        sent_total = 0

        while True:
            now = time.perf_counter()
            if now >= end_time:
                break

            try:
                record = next(iterator)
            except StopIteration:
                break

            # Inter-arrival (jitter)
            if self._last_send_time is not None:
                self.metrics.inter_arrivals.append(now - self._last_send_time)
            self._last_send_time = now

            payload_str = json.dumps(record, separators=(",", ":"))

            #  MQTT 
            if args.out in ("mqtt", "both"):
                info = self.mqtt.publish(args.mqtt_topic, payload_str, qos=1, retain=False)
                self.inflight_mqtt[info.mid] = now
                self.metrics.sent_mqtt += 1

            #  Kafka 
            if args.out in ("kafka", "both"):
                self._kafka_sid_seq += 1
                sid = str(self._kafka_sid_seq)
                self.inflight_kafka[sid] = now
                hdrs = [("sid", sid.encode())] 
                
                try:
                    self.kafka.produce(
                        args.kafka_topic,
                        key=sid,
                        value=payload_str.encode(),
                        headers=hdrs,
                        callback=self._delivery_report
                    )
                except BufferError:
                    self.kafka.poll(0.1)
                    self.kafka.produce(
                        args.kafka_topic,
                        key=sid,
                        value=payload_str.encode(),
                        headers=hdrs,
                        callback=self._delivery_report
                    )
                self.metrics.sent_kafka += 1
                self.kafka.poll(0)

            sent_total += 1
            send_window.append(now)
            while send_window and (now - send_window[0] > self.window_sec):
                send_window.popleft()

            # Periodic status
            if (now - last_status_t) >= self.status_every:
                qps_inst = len(send_window) / self.window_sec
                jitter = pstdev(self.metrics.inter_arrivals) if self.metrics.inter_arrivals else 0.0
                p95_k = percentile(self.metrics.kafka_latencies, 95) or 0.0
                p95_m = percentile(self.metrics.mqtt_latencies, 95) or 0.0
                print(
                    f"[status] t+{now - start:6.2f}s  qps~{qps_inst:6.2f}  jitter~{jitter:.6f}s  "
                    f"kafka sent/ack/lost={self.metrics.sent_kafka}/{self.metrics.acked_kafka}/{self.metrics.lost_kafka} "
                    f"(p95={p95_k*1000:.1f}ms)  "
                    f"mqtt sent/ack/lost={self.metrics.sent_mqtt}/{self.metrics.acked_mqtt}/{self.metrics.lost_mqtt} "
                    f"(p95={p95_m*1000:.1f}ms)"
                )
                last_status_t = now

            # Metronome to target QPS
            elapsed = now - start
            target_elapsed = sent_total * interval
            sleep_for = target_elapsed - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)

        # Drain & close
        self.kafka.flush()
        try:
            self.mqtt.loop_stop()
        finally:
            self.mqtt.disconnect()

        # Summary
        runtime = time.perf_counter() - start
        qps_avg = sent_total / runtime if runtime > 0 else 0.0

        p50_k = percentile(self.metrics.kafka_latencies, 50)
        p95_k = percentile(self.metrics.kafka_latencies, 95)
        p99_k = percentile(self.metrics.kafka_latencies, 99)
        p50_m = percentile(self.metrics.mqtt_latencies, 50)
        p95_m = percentile(self.metrics.mqtt_latencies, 95)
        p99_m = percentile(self.metrics.mqtt_latencies, 99)
        jitter = pstdev(self.metrics.inter_arrivals) if self.metrics.inter_arrivals else None

        print("[summary]")
        print(f"  total: sent={sent_total} runtime={runtime:.2f}s qps_avg≈{qps_avg:.2f}")
        print(f"  jitter (std of inter-arrival): {jitter:.6f}s")
        print(
            "  kafka: "
            f"sent={self.metrics.sent_kafka} acked={self.metrics.acked_kafka} lost={self.metrics.lost_kafka} "
            f"p50/p95/p99={fmt_latency(p50_k)}/{fmt_latency(p95_k)}/{fmt_latency(p99_k)}"
        )
        print(
            "  mqtt : "
            f"sent={self.metrics.sent_mqtt} acked={self.metrics.acked_mqtt} lost={self.metrics.lost_mqtt} "
            f"p50/p95/p99={fmt_latency(p50_m)}/{fmt_latency(p95_m)}/{fmt_latency(p99_m)}"
        )

        losses = self.metrics.loss_rates()
        print(f"  kafka loss: {losses['kafka_loss_pct']:.3f}%")
        print(f"  mqtt  loss: {losses['mqtt_loss_pct']:.3f}%")
