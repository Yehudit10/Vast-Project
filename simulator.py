from __future__ import annotations

import argparse
import json
from collections import deque
from statistics import pstdev
import time
from typing import Dict, Optional

import pandas as pd

from drivers import DummyKafkaProducer, DummyMQTTClient
from metrics import Metrics
from utils import iterate_records, percentile, fmt_latency, extract_sid_from_headers
from confluent_kafka import Producer

class Simulator:
    """
    Encapsulates the send loop, rate control, and metrics aggregation.
    WHY: Using a class removes globals, makes testing easier, and keeps main() tidy.
    """

    def __init__(self, args: argparse.Namespace, df: pd.DataFrame):
        self.args = args
        self.df = df

        # Transports (Dummy for now)
        self.mqtt = DummyMQTTClient(client_id="simulator")
        # self.kafka = DummyKafkaProducer()

        conf = {
            "bootstrap.servers": "localhost:9094", 
            "client.id": "simulator"
        }
        self.kafka = Producer(conf)
        
        # Inflight maps: mid/sid -> send_time
        self.inflight_mqtt: Dict[int, float] = {}
        self.inflight_kafka: Dict[str, float] = {}

        self.metrics = Metrics()

        # Rate control / status
        self.window_sec = float(args.window_sec)
        self.status_every = float(args.status_every)

        # Internal bookkeeping
        self._kafka_sid_seq = 0
        self._last_send_time: Optional[float] = None

        # Attach callbacks
        self.mqtt.on_publish = self._on_mqtt_publish

    # --- Callbacks ---

    def _delivery_report(self, err, msg):
        """
        Kafka delivery callback: update ack counters and latency.
        """
        if err is None:
            self.metrics.acked_kafka += 1
            # Match 'sid' header to inflight send timestamp
            try:
                sid = extract_sid_from_headers(getattr(msg, "headers", lambda: None)())
            except Exception:
                sid = None
            if sid and sid in self.inflight_kafka:
                start_ts = self.inflight_kafka.pop(sid, None)
                if start_ts is not None:
                    self.metrics.kafka_latencies.append(time.perf_counter() - start_ts)
        else:
            self.metrics.lost_kafka += 1

    def _on_mqtt_publish(self, client, userdata, mid):
        """
        MQTT publish callback (simulated here): update ack counters and latency.
        """
        self.metrics.acked_mqtt += 1
        start_ts = self.inflight_mqtt.pop(mid, None)
        if start_ts is not None:
            self.metrics.mqtt_latencies.append(time.perf_counter() - start_ts)

    # --- Core run ---

    def run(self) -> None:
        """
        Execute the main send loop honoring QPS & duration; print status and summary.
        """
        args = self.args

        # MQTT connect (dummy)
        self.mqtt.connect(args.mqtt_host, args.mqtt_port)

        # Record iterator: optionally loop
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
                # No looping and we exhausted the sample -> stop.
                break

            # Inter-arrival measurement (for jitter)
            if self._last_send_time is not None:
                self.metrics.inter_arrivals.append(now - self._last_send_time)
            self._last_send_time = now

            payload_str = json.dumps(record, separators=(",", ":"))

            # --- MQTT ---
            if args.out in ("mqtt", "both"):
                rc, mid = self.mqtt.publish(args.mqtt_topic, payload_str, qos=1)
                self.inflight_mqtt[mid] = now
                self.metrics.sent_mqtt += 1
                self.mqtt.poll()

            # --- Kafka ---
            if args.out in ("kafka", "both"):
                self._kafka_sid_seq += 1
                sid = str(self._kafka_sid_seq)
                self.inflight_kafka[sid] = now
                hdrs = [("sid", sid.encode())]  # WHY: match delivery to send time.
                try:
                    self.kafka.produce(
                        args.kafka_topic,
                        key=str(record.get("device_id") or ""),
                        value=payload_str.encode(),
                        headers=hdrs,
                        callback=self._delivery_report
                    )
                except BufferError:
                    # WHY: On a real producer buffer full, poll then retry keeping headers & sid.
                    self.kafka.poll(0.1)
                    self.kafka.produce(
                        args.kafka_topic,
                        key=str(record.get("device_id") or ""),
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

            # Metronome: keep average QPS close to target
            elapsed = now - start
            target_elapsed = sent_total * interval
            sleep_for = target_elapsed - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)

        # Drain & close
        self.kafka.flush()
        self.mqtt.disconnect()

        # Final summary
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
