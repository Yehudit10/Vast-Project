import os
import io
import json
import time
import logging
import imghdr
import requests
from requests.adapters import HTTPAdapter, Retry
from minio import Minio
from PIL import Image

from pyflink.datastream import StreamExecutionEnvironment
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.common import WatermarkStrategy
from pyflink.datastream.connectors.kafka import (
    KafkaSource,
    KafkaSink,
    KafkaRecordSerializationSchema,
    KafkaOffsetsInitializer
)
from pyflink.datastream.functions import RuntimeContext, ProcessFunction


# ===============================================================
#                       LOGGER CONFIGURATION
# ===============================================================
def setup_logger():
    logger = logging.getLogger("FlinkJob")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s",
                                           "%Y-%m-%d %H:%M:%S"))
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    return logger

def upload_to_minio(file_path, bucket_name, object_name):
    try:
        endpoint = os.getenv("MINIO_ENDPOINT", "minio-hot:9000")
        access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
        use_ssl = False
        client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=use_ssl)
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            logging.info(f"🪣 Created bucket '{bucket_name}'")
        client.fput_object(bucket_name, object_name, file_path)
        logging.info(f"✅ Uploaded {object_name} to bucket '{bucket_name}'")
    except Exception as e:
        logging.error(f"❌ MinIO upload failed: {e}")



logger = setup_logger()


# ===============================================================
#                 DownloadAndInfer Process Function
# ===============================================================
class DownloadAndInfer(ProcessFunction):
    """Kafka → MinIO → Segmentation API → Infer API → Anomaly API → Kafka"""

    def open(self, runtime_context: RuntimeContext):
        self.minio_client = Minio(
            endpoint=os.getenv("MINIO_ENDPOINT", "minio-hot:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
            secure=False
        )

        self.segmentation_url = os.getenv("SEGMENTATION_URL", "http://segmentation-api:8500/infer")
        self.infer_url = os.getenv("INFER_URL", "http://infer-api:8000/infer")
        self.anomaly_url = os.getenv("ANOMALY_URL", "http://anomaly-api:8010/predict")

        self.conf = float(os.getenv("INFER_CONF", "0.25"))
        self.iou = float(os.getenv("INFER_IOU", "0.45"))
        self.tmp_dir = "/opt/app/tmp"
        os.makedirs(self.tmp_dir, exist_ok=True)

        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
        self.session.mount("http://", HTTPAdapter(max_retries=retries))
        self.timeout = (5, 180)

        logger.info("✅ DownloadAndInfer ready (Segmentation + Object + Anomaly)")

    def process_element(self, value, ctx):
        infer_results, anomaly_results, segmentation_results = [], [], []
        logger.info("\n" + "=" * 70)
        logger.info(f"📥 Received message: {value}")

        total_start = time.time()

        # === Parse Kafka message ===
        try:
            data = json.loads(value)
            image_key = data.get("img_key")
            if not image_key:
                logger.warning("⚠️ Missing 'key' in Kafka message")
                return []
        except Exception as e:
            logger.warning(f"⚠️ Invalid JSON: {e}")
            return []

        bucket, *path_parts = image_key.strip("/").split("/")
        object_path = "/".join(path_parts)
        local_filename = os.path.basename(object_path)
        local_path = os.path.join(self.tmp_dir, local_filename)

        # === Step 1: Download from MinIO ===
        try:
            self.minio_client.fget_object(bucket, object_path, local_path)
            logger.info(f"✅ Downloaded: {bucket}/{object_path}")
        except Exception as e:
            logger.error(f"❌ Failed to download from MinIO: {e}")
            return []

        # === Step 2: Detect MIME ===
        try:
            with open(local_path, "rb") as f:
                img_bytes = f.read()
            image_type = imghdr.what(None, h=img_bytes)
            if not image_type:
                img = Image.open(io.BytesIO(img_bytes))
                image_type = img.format.lower()
            mime_type = f"image/{'jpeg' if image_type == 'jpg' else image_type}"
            file_name = f"image.{image_type}"
            logger.info(f"🧾 Detected image type: {image_type.upper()}")
        except Exception as e:
            logger.error(f"❌ Invalid image: {e}")
            return []

        # === Step 3: Segmentation API ===
        try:
            files = {"file": (file_name, img_bytes, mime_type)}
            logger.info(f"🛰️ Sending to Segmentation API: {self.segmentation_url}")
            t0 = time.time()
            r_seg = self.session.post(self.segmentation_url, files=files, timeout=self.timeout)
            t1 = time.time() - t0
            r_seg.raise_for_status()

            base_name = os.path.splitext(local_filename)[0]
            mask_filename = f"{base_name}_mask.png"
            mask_path = os.path.join(self.tmp_dir, mask_filename)
            mask_bytes = r_seg.content
            if not r_seg.content:
                logger.warning(f"⚠️ Segmentation API returned empty mask for {image_key}")
            with open(mask_path, "wb") as f:
                f.write(mask_bytes)
            logger.info(f"🖼️ Saved segmentation mask: {mask_path}")

            # === Step 3.1: Upload mask to MinIO ===
            try:
                bucket_name = os.getenv("MINIO_BUCKET", "imagery")
                mask_object_key = f"air_mask/{mask_filename}"   
                upload_to_minio(mask_path, bucket_name, mask_object_key)
                logger.info(f"☁️ Uploaded mask to MinIO at {bucket_name}/{mask_object_key}")
            except Exception as e:
                logger.error(f"❌ Failed to upload mask to MinIO: {e}")

            header_data = r_seg.headers.get("X-Class-Distribution")
            if header_data:
                dist = json.loads(header_data.replace("'", '"'))
            else:
                dist = {}

            row = {
                "img_key": image_key,
                "mask_path": f"{bucket_name}/{mask_object_key}",
                "other": dist.get("Other", 0),
                "bareland": dist.get("Bareland", 0),
                "rangeland": dist.get("Rangeland", 0),
                "developed_space": dist.get("Developed space", 0),
                "road": dist.get("Road", 0),
                "tree": dist.get("Tree", 0),
                "water": dist.get("Water", 0),
                "agriculture": dist.get("Agriculture land", 0),
                "building": dist.get("Building", 0),
            }

            segmentation_results.append(row)
            logger.info(f"🧩 Segmentation done for {image_key}: {json.dumps(row, indent=2)}")

        except Exception as e:
            logger.exception(f"❌ Segmentation API error: {e}")
            mask_path = None

        # === Step 4: Object Detection (Infer API) ===
        try:
            files = {"image": (file_name, img_bytes, mime_type)}

            if mask_path and os.path.exists(mask_path):
                with open(mask_path, "rb") as f:
                    mask_bytes = f.read()
                files["mask"] = (os.path.basename(mask_path), mask_bytes, "image/png")
                logger.info(f"🧠 Using segmentation mask for Infer API: {mask_path}")

            params = {"conf": self.conf, "iou": self.iou}
            t0 = time.time()
            r = self.session.post(self.infer_url, files=files, params=params, timeout=self.timeout)
            t1 = time.time() - t0

            r.raise_for_status()
            infer_data = r.json() if r.status_code != 204 else {}
            infer_detections = infer_data.get("result", {}).get("detections", []) or infer_data.get("detections", [])
            for det in infer_detections:
                x1, y1, x2, y2 = det.get("bbox", [0, 0, 0, 0])
                infer_results.append({
                    "img_key": image_key,
                    "label": det.get("class_name"),
                    "confidence": float(det.get("confidence", 0)),
                    "bbox_x1": float(x1),
                    "bbox_y1": float(y1),
                    "bbox_x2": float(x2),
                    "bbox_y2": float(y2)
                })
            logger.info(f"🧠 {image_key}: {len(infer_detections)} detections ({t1:.2f}s)")
        except Exception as e:
            logger.exception(f"❌ Infer API error: {e}")

        # === Step 5: Anomaly API ===
        res = {}
        try:
            files = {"file": (file_name, img_bytes, mime_type)}
            t2 = time.time()
            r2 = self.session.post(self.anomaly_url, files=files, timeout=self.timeout)
            t3 = time.time() - t2

            r2.raise_for_status()
            res = r2.json()
            if res.get("anomaly", False):
                detections = res.get("detections", [])
                for det in detections:
                    x1, y1, x2, y2 = det.get("bbox", [0, 0, 0, 0])
                    anomaly_results.append({
                        "img_key": image_key,
                        "label": det.get("label", "anomaly"),
                        "confidence": float(det.get("confidence", 0)),
                        "bbox_x1": float(x1),
                        "bbox_y1": float(y1),
                        "bbox_x2": float(x2),
                        "bbox_y2": float(y2)
                    })
                logger.info(f"⚠️ Anomaly detection: {len(detections)} anomalies ({t3:.2f}s)")
            else:
                logger.info("✅ No anomalies detected.")
        except Exception as e:
            logger.exception(f"❌ Anomaly API error: {e}")
        
        # === step 6: alerts ====
        alert_events = []

        if res.get("anomaly", False):
            detections = res.get("detections", [])

            # Extract device_id from filename
            filename = os.path.basename(image_key)
            device_id = filename.split("_")[0]

            alert = {
                "alert_id": f"{time.time_ns()}",
                "alert_type": "aerial_anomaly_detected",
                "device_id": device_id,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "confidence": max(d.get("confidence", 0) for d in detections),
                "severity": 3,
                "image_url": image_key,     # key = url אצלך
                "meta": {
                    "anomalies": detections
                }
            }

            alert_events.append((json.dumps(alert), "alert"))
            logger.info(f"🚨 ALERT created: {json.dumps(alert, indent=2)}")

        # === Step 7: Clean temp ===
        try:
            os.remove(local_path)
            if mask_path and os.path.exists(mask_path):
                os.remove(mask_path)
        except Exception:
            pass

        total_time = time.time() - total_start

        logger.info(f"📊 Summary: "
            f"{len(segmentation_results)} segmentations, "
            f"{len(infer_results)} detections, "
            f"{len(anomaly_results)} anomalies")
        
        logger.info(f"⏱️ Total processing time for {image_key}: {total_time:.2f}s")

        return ([(json.dumps(r), "segmentation") for r in segmentation_results] +
                [(json.dumps(r), "object") for r in infer_results] +
                [(json.dumps(r), "anomaly") for r in anomaly_results]+
                alert_events)


# ===============================================================
#                       MAIN EXECUTION FUNCTION
# ===============================================================
def main():
    logger.info("🚀 Starting Kafka→MinIO→Segmentation→Infer→Anomaly→Kafka Job")

    bootstrap = os.getenv("KAFKA_BROKERS", "kafka:9092")
    topic_in = os.getenv("IN_TOPIC", "image.new.aerial")
    topic_out_segmentation = os.getenv("OUT_TOPIC_SEGMENTATION", "aerial_image_segmentation")
    topic_out_objects = os.getenv("OUT_TOPIC_OBJECT", "aerial_image_object_detections")
    topic_out_anomaly = os.getenv("OUT_TOPIC_ANOMALY", "aerial_image_anomaly_detections")
    topic_out_alerts = os.getenv("OUT_TOPIC_ALERTS", "alerts")
    group_id = os.getenv("KAFKA_GROUP_ID", f"flink-air-device-pipeline")

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(bootstrap)
        .set_topics(topic_in)
        .set_group_id(group_id)
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    sink_segmentation = (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(topic_out_segmentation)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )

    sink_objects = (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(topic_out_objects)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )

    sink_anomalies = (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(topic_out_anomaly)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )

    sink_alerts = (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(topic_out_alerts)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )


    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "Kafka Source")

    processed = stream.process(DownloadAndInfer(), output_type=Types.TUPLE([Types.STRING(), Types.STRING()]))

    segmentation_stream = processed.filter(lambda x: x[1] == "segmentation").map(lambda x: x[0], output_type=Types.STRING())
    objects_stream = processed.filter(lambda x: x[1] == "object").map(lambda x: x[0], output_type=Types.STRING())
    anomalies_stream = processed.filter(lambda x: x[1] == "anomaly").map(lambda x: x[0], output_type=Types.STRING())
    alerts_stream = processed.filter(lambda x: x[1] == "alert").map(lambda x: x[0], output_type=Types.STRING())

    segmentation_stream.sink_to(sink_segmentation)
    objects_stream.sink_to(sink_objects)
    anomalies_stream.sink_to(sink_anomalies)
    alerts_stream.sink_to(sink_alerts)


    env.execute("Kafka-MinIO-Segmentation-Infer-Anomaly-Job")


if __name__ == "__main__":
    main()
