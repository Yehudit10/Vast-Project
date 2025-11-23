import os, json, math, logging
import pandas as pd
from statistics import mean, median, stdev
from pyflink.common import Types, Time
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaSink, KafkaRecordSerializationSchema
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.datastream.window import SlidingProcessingTimeWindows
from pyflink.datastream.functions import WindowFunction
from shapely.geometry import shape, Point
from pathlib import Path
from typing import Optional
from sensorAnomalyPro.profiles_runtime import load_profiles, StreamingState, score_new_point
from datetime import datetime, timezone
import json
from statistics import mean, median, stdev



# --- Config ---
OUT_TOPIC = os.getenv("OUT_TOPIC", "sensor_anomalies")
ZONE_TOPIC = os.getenv("ZONE_TOPIC", "sensor-zone-stats")
ZONES_PATH = Path(__file__).resolve().parent / "zones.geojson"
AGG_INTERVAL = int(os.getenv("ZONE_AGG_INTERVAL_SEC", "300"))
SLIDE_INTERVAL = int(os.getenv("ZONE_SLIDE_INTERVAL_SEC", "60"))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("sensor-anomaly")

# --- Zones loading ---
_zones = []
def load_zones():
    global _zones
    try:
        p = Path(ZONES_PATH)
        if not p.exists():
            log.warning(f"zones file not found: {ZONES_PATH}")
            return
        gj = json.loads(p.read_text(encoding="utf-8"))
        feats = gj.get("features", [])
        _zones = [(shape(f["geometry"]), f["properties"].get("name", f"zone_{i}")) for i, f in enumerate(feats)]
        log.info(f"Loaded {len(_zones)} zones from {ZONES_PATH}")
    except Exception as e:
        log.warning(f"zones disabled: {e}")
        _zones = []

load_zones()


def resolve_zone(lat, lon) -> Optional[str]:
    if not _zones or lat is None or lon is None:
        return None
    try:
        pt = Point(lon, lat)
        for poly, name in _zones:
            if poly.contains(pt):
                return name
        return None
    except Exception:
        return None


# --- Helpers ---
_profiles_cache = {}
_states = {}

def _norm_float(x: Optional[float]) -> Optional[float]:
    try:
        fx = float(x)
        return fx if math.isfinite(fx) else None
    except Exception:
        return None

def _finite_or_none(x):
    try:
        fx = float(x)
        return fx if math.isfinite(fx) else None
    except Exception:
        return None

def _valid_latlon(lat: Optional[float], lon: Optional[float]) -> bool:
    return lat is not None and lon is not None and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0

def _classify_condition(sensor: str, value: float, lower: float, upper: float) -> str:
    if sensor == "Soil_Moisture":
        if value < lower: return "dry"
        elif value > upper: return "wet"
    elif sensor == "Ambient_Temperature":
        if value < lower: return "cold"
        elif value > upper: return "hot"
    elif sensor == "Humidity":
        if value < lower: return "low_humidity"
        elif value > upper: return "high_humidity"
    return "normal"


# --- Anomaly detection ---
def detect_anomaly(evt: dict) -> dict:
    plant_id, sensor = evt.get("plant_id"), evt.get("sensor_name")
    key = (plant_id, sensor)

    if evt.get("value") is None:
        return {"ok": False, "reason": "no_value"}

    prof = _profiles_cache.get(key)
    if prof is None:
        prof = load_profiles(plant_id, sensor)
        if not prof:
            return {"ok": False, "reason": "no_profiles"}
        _profiles_cache[key] = prof

    state = _states.get(key)
    if state is None:
        state = StreamingState(alpha=0.08)
        _states[key] = state

    try:
        ts_str = evt.get("timestamp") or evt.get("ts")
        ts = pd.Timestamp(ts_str)
    except Exception:
        return {"ok": False, "reason": "bad_ts"}

    res = score_new_point(ts=ts, value=evt.get("value"),
                          profiles=prof, state=state,
                          k_band=2.0, spike_z_like=3.0, break_mult=1.5)
    if not res.get("ok", False):
        return {"ok": False, "reason": res.get("reason", "unknown")}

    condition = _classify_condition(sensor, evt.get("value"), res["lower"], res["upper"])
    return {
        "ok": True,
        "is_anomaly": bool(res["is_anomaly"]),
        "bl_type": str(res["bl_type"]),
        "baseline": _finite_or_none(res["baseline"]),
        "adaptive_baseline": _finite_or_none(res.get("adaptive_baseline")),
        "bias": _finite_or_none(res.get("bias")),
        "lower": _finite_or_none(res["lower"]),
        "upper": _finite_or_none(res["upper"]),
        "band_std": _finite_or_none(res["band_std"]),
        "flags": {k: bool(v) for k, v in res["flags"].items()},
        "ema_abs_res": _finite_or_none(res.get("ema_abs_res")),
        "ts": str(res["ts"]),
        "condition": condition
    }


# --- Map events ---
def process_event(raw: str):
    try:
        evt = json.loads(raw)
    except json.JSONDecodeError:
        return None

    lat = _norm_float(evt.get("lat"))
    lon = _norm_float(evt.get("lon"))
    if not _valid_latlon(lat, lon):
        lat, lon = None, None

    zone_name = resolve_zone(lat, lon)
    res = detect_anomaly(evt)
    if not res.get("ok", True):
        return None

    out = {
        "idsensor": evt.get("sensor_id"),
        "plant_id": evt.get("plant_id"),
        "sensor": evt.get("sensor_name"),
        "ts": evt.get("timestamp") or evt.get("ts"),
        "value": evt.get("value"),
        "lat": lat,
        "lon": lon,
        "zone": zone_name,
        "result": res
    }
    return json.dumps(out)


# --- Zone window aggregator (new API) ---



class ZoneAggregator(WindowFunction):
    def apply(self, key, window, inputs):
        values = []
        anomalies = 0

        for e in inputs:
            evt = json.loads(e)
            if evt.get("value") is not None:
                values.append(evt["value"])
            if evt["result"].get("is_anomaly"):
                anomalies += 1

        if not values:
            return []
 
        window_start = datetime.fromtimestamp(window.start / 1000, tz=timezone.utc).isoformat()
        window_end = datetime.fromtimestamp(window.end / 1000, tz=timezone.utc).isoformat()

        result = {
            "zone": key,
            "window_start": window_start,
            "window_end": window_end,
            "count": len(values),
            "mean": mean(values),
            "median": median(values),
            "min": min(values),
            "max": max(values),
            "std": stdev(values) if len(values) > 1 else 0.0,
            "anomalies": anomalies
        }

        log.info(f"[ZoneAggregator] zone={key}, count={len(values)}, anomalies={anomalies}")
        return [json.dumps(result)]

# --- Main ---
def main():
    brokers = os.getenv("KAFKA_BROKERS", "kafka:9092")
    in_topic = os.getenv("IN_TOPIC", "sensors")

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(int(os.getenv("FLINK_PARALLELISM", "2")))

    source = KafkaSource.builder() \
        .set_bootstrap_servers(brokers) \
        .set_topics(in_topic) \
        .set_group_id("flink-anomaly-detector") \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()

    sink_anomalies = KafkaSink.builder() \
        .set_bootstrap_servers(brokers) \
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(OUT_TOPIC)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        ).build()

    sink_zones = KafkaSink.builder() \
        .set_bootstrap_servers(brokers) \
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(ZONE_TOPIC)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        ).build()

    ds = env.from_source(source, WatermarkStrategy.no_watermarks(), "kafka-in")

    processed = ds.map(process_event, output_type=Types.STRING()) \
                  .filter(lambda x: x is not None)

    processed.sink_to(sink_anomalies)

    zone_summary = processed \
        .filter(lambda s: json.loads(s).get("zone") is not None) \
        .key_by(lambda s: json.loads(s)["zone"]) \
        .window(SlidingProcessingTimeWindows.of(Time.seconds(AGG_INTERVAL),
                                                Time.seconds(SLIDE_INTERVAL))) \
        .apply(ZoneAggregator(), output_type=Types.STRING())

    zone_summary.sink_to(sink_zones)

    env.execute("sensor-anomaly-job")


if __name__ == "__main__":
    main()
