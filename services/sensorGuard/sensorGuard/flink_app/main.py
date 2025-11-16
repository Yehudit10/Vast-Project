import os, json, yaml, threading, time
from datetime import datetime, timezone
from pathlib import Path

from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.common.typeinfo import Types
from pyflink.datastream.functions import MapFunction, ProcessFunction, RuntimeContext

from core.engine import Engine
from core.types import Event
from io_mod.writer_console import ConsoleWriter
from io_mod.writer_kafka import KafkaWriter
from api.auth import get_access_token
from api.devices_client import list_active_sensors
from core.state import StateStore


DROP_INVALID = True


# -------------------------------------------------------------
# Convert incoming Kafka message to Event
# -------------------------------------------------------------
def to_event(obj: dict) -> Event | None:
    if not isinstance(obj, dict):
        print("[to_event] Invalid object type, expected dict.")
        return None

    ts = datetime.now(timezone.utc)
    device_id = obj.get("id")
    sensor_type = obj.get("sensor_type") or obj.get("sensor_name", "unknown_sensor")

    if not device_id:
        if DROP_INVALID:
            print("[to_event] Dropping event due to missing device_id.")
            return None
        device_id = "unknown_device"
    else:
        device_id = str(device_id)

    value_str = obj.get("value")
    try:
        value = float(value_str) if value_str is not None else None
    except ValueError:
        print(f"[to_event] Invalid numeric value: {value_str}")
        value = None

    print(f"[to_event] Parsed event: device_id={device_id}, sensor_type={sensor_type}")

    return Event(
        ts=ts,
        device_id=device_id,
        sensor_type=sensor_type,
        site_id=obj.get("site_id"),
        msg_type=obj.get("msg_type", "reading"),
        value=value,
        seq=obj.get("seq"),
        quality=obj.get("quality"),
    )


# -------------------------------------------------------------
# Engine Mapper: applies Engine logic for each event
# -------------------------------------------------------------
class EngineMapper(MapFunction):
    def __init__(self, cfg_path: str, state: StateStore):
        self.cfg_path = cfg_path
        self.state = state
        self.engine = None

    def open(self, runtime_context: RuntimeContext):
        with open(self.cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        writers = [ConsoleWriter(), KafkaWriter()]
        self.engine = Engine(cfg, writers, state=self.state)

    def map(self, ev: Event) -> str:
        if ev is None:
            return ""
        print(f"[EngineMapper] Processing event for device_id={ev.device_id}")
        self.engine.process_event(ev)
        return ev.device_id or ""


# -------------------------------------------------------------
# Silence Sweep Process (background thread)
# -------------------------------------------------------------
class SilenceSweepProcess(ProcessFunction):
    def __init__(self, cfg_path: str, interval_sec: int, state: StateStore):
        self.cfg_path = cfg_path
        self.interval_sec = interval_sec
        self.state = state
        self.engine = None
        self._thread = None
        self._stop = False

    def open(self, runtime_context: RuntimeContext):
        print("[SilenceSweepProcess] Initializing background silence checker.")
        with open(self.cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        writers = [ConsoleWriter(), KafkaWriter()]
        self.engine = Engine(cfg, writers, state=self.state)

        # Run silence sweep periodically in a separate thread
        def loop():
            print(f"[SilenceSweep] Thread started! Interval={self.interval_sec}s")
            time.sleep(self.interval_sec)
            while not self._stop:
                now = datetime.now(timezone.utc)
                print(f"[SilenceSweep] Checking silence at {now.isoformat()}")
                try:
                    self.engine.sweep_silence(now)
                    print("[SilenceSweep] Sweep completed.")
                except Exception as e:
                    print(f"[SilenceSweep][ERROR] {e}")
                time.sleep(self.interval_sec)
            print("[SilenceSweep] Thread stopped.")

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def close(self):
        self._stop = True
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def process_element(self, value, ctx: 'ProcessFunction.Context'):
        # No per-event logic needed
        pass


# -------------------------------------------------------------
# Main entry point
# -------------------------------------------------------------
def main():
    print("=== STARTING FLINK APPLICATION ===")
    base_dir = Path(__file__).resolve().parent
    cfg_path = base_dir / "config" / "rules.yaml"

    # --- Load sensors from API ---
    api_base = os.getenv("DEVICES_API_BASE", "http://host.docker.internal:8001")
    print(f"[INIT] Fetching active sensors from {api_base}...")

    token = get_access_token(api_base)
    print(f"[INIT] Token received: {'YES' if token else 'NO'}")

    shared_state = StateStore()
    if token:
        for device_id in list_active_sensors(api_base, token):
            shared_state.add_device(device_id)
        print(f"[INIT] Loaded {len(shared_state.devices)} active sensors.")
    else:
        print("[INIT][WARN] No token, running with empty device list.")

    # --- Flink Setup ---
    bootstrap = os.getenv("KAFKA_BROKERS", "kafka:9092")
    topic_in = os.getenv("IN_TOPIC", "sensors")
    group_id = os.getenv("KAFKA_GROUP_ID", "flink-device-pipeline")

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    env.enable_checkpointing(10_000)

    # Kafka source
    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(bootstrap)
        .set_topics(topic_in)
        .set_group_id(group_id)
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    stream = env.from_source(
        source,
        WatermarkStrategy.no_watermarks(),
        f"kafka-source:{topic_in}"
    )

    # --- Processing pipeline ---
    def parse_json(s: str):
        try:
            parsed = json.loads(s)
            print(f"[FLINK-KAFKA] Parsed JSON: {s[:100]}...")
            return parsed
        except Exception as e:
            print(f"[FLINK-KAFKA] Parse error: {e}")
            return None

    events = (
        stream.map(parse_json)
        .filter(lambda e: e is not None)
        .map(to_event)
        .filter(lambda e: e is not None)
    )

    # --- Apply Engine ---
    mapper = EngineMapper(str(cfg_path), shared_state)
    mapped = events.map(mapper, output_type=Types.STRING()).name("engine-run")
    mapped.print().name("debug-print")

    # --- Silence check background thread ---
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    interval = cfg.get("defaults", {}).get("silence_sweep_interval_seconds", 300)

    silence_checker = SilenceSweepProcess(str(cfg_path), interval, shared_state)
    events.process(silence_checker).name("silence-sweeper")

    print("[INIT] Starting Flink job...")
    env.execute("DevicePipeline-With-SilenceSweep")


if __name__ == "__main__":
    print("=== FLINK MAIN.PY EXECUTED ===")
    main()
