import os
import json
import joblib
import pandas as pd
import numpy as np
from pyflink.common import Types
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaSink, KafkaRecordSerializationSchema
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.datastream.functions import MapFunction, RuntimeContext


# --- ENV VARS ---
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka:9092")
IN_TOPIC = os.getenv("IN_TOPIC", "sensors")
OUT_TOPIC = os.getenv("OUT_TOPIC", "sensors_anomalies_modal")

ART_IFOREST_PCA = os.getenv("ART_IFOREST_PCA", "/opt/models/iforest_pca_artifacts.joblib")
ART_RESIDUALS = os.getenv("ART_RESIDUALS", "/opt/models/residuals_artifacts.joblib")


# --- MAIN MAPPER CLASS ---
class AnomalyMap(MapFunction):
    def open(self, ctx: RuntimeContext):
        print(">>> Loading models...")
        self.ifp = joblib.load(ART_IFOREST_PCA)
        self.res = joblib.load(ART_RESIDUALS)

        self.pre = self.ifp["pre"]
        self.ifr = self.ifp["iforest"]
        self.pca = self.ifp["pca"]
        self.pthr = self.ifp["pca_thr"]
        self.fcols = self.ifp["feature_cols"]
        self.num = self.ifp.get("num_cols", self.res.get("num_cols", []))
        self.rmdl = self.res["resid_models"]
        self.rthr = self.res["resid_thr"]

        print(f">>> Models loaded successfully with {len(self.fcols)} features.")

    def map(self, raw: str):
        print("\n=== RAW MESSAGE START ===")
        print(raw)
        print("=== RAW MESSAGE END ===\n")

        try:
            evt = json.loads(raw)
            if isinstance(evt, str):
                evt = json.loads(evt)
        except Exception as e:
            print(f"[warning] Failed parsing message: {e}, raw={raw!r}")
            return None

        if not isinstance(evt, dict):
            print(f"[warning] Unexpected event type: {type(evt)} => {evt}")
            return None

        print("PARSED EVENT KEYS:", list(evt.keys()))

        try:
            row = {c: evt.get(c, np.nan) for c in self.fcols}
            df = pd.DataFrame([row])
            df = df.replace(["unknown", ""], np.nan)

            for c in self.num:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
                else:
                    df[c] = np.nan

            for c in self.num:
                if c in df.columns:
                    median = df[c].median()
                    df[c] = df[c].fillna(median)

            print("DEBUG >>>", df.dtypes.to_dict())
            print("HEAD >>>", df.head().to_dict(orient="records"))

            X = self.pre.transform(df)
            iflag = int(self.ifr.predict(X)[0] == -1)

            # ------------------------------------------------
            # FIXED SENSOR ID HANDLING
            # ------------------------------------------------
            sensor_id = evt.get("id")

            # Fallback: if only "sid": "sensor-12" exists
            if sensor_id is None:
                sid = evt.get("sid")
                if isinstance(sid, str) and sid.startswith("sensor-"):
                    try:
                        sensor_id = int(sid.replace("sensor-", ""))
                    except:
                        sensor_id = None

            if sensor_id is None:
                print("[warning] Missing valid sensor_id, event skipped")
                return None

            result = {
                "sensor_id": int(sensor_id),
                "ts": evt.get("ts", evt.get("timestamp")),
                "anomaly": iflag
            }

            print("OUTPUT:", result)
            return json.dumps(result)

        except Exception as e:
            print(f"[error] Failed processing message: {e}, evt={evt}")
            return None


# --- MAIN EXECUTION ---
def main():
    print("Brokers:", KAFKA_BROKERS)
    print("In:", IN_TOPIC, "Out:", OUT_TOPIC)

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(2)

    source = KafkaSource.builder() \
        .set_bootstrap_servers(KAFKA_BROKERS) \
        .set_topics(IN_TOPIC) \
        .set_group_id("flink-anomaly") \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()

    sink = KafkaSink.builder() \
        .set_bootstrap_servers(KAFKA_BROKERS) \
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(OUT_TOPIC)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        ).build()

    ds = env.from_source(source, WatermarkStrategy.no_watermarks(), "kafka-in")
    ds.map(AnomalyMap(), output_type=Types.STRING()) \
      .filter(lambda x: x is not None) \
      .sink_to(sink)

    env.execute("sensor-anomaly-stream")


if __name__ == "__main__":
    main()
