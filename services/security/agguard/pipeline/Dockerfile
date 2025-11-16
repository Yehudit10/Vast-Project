
# syntax=docker/dockerfile:1.6

############################################################
# Stage 1 — Build Python virtual environment inside Flink base
############################################################
FROM flink:1.19.3-scala_2.12-java11 AS builder

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENCV_OPENCL_RUNTIME=disabled

# ─── System dependencies (for OpenCV, Torch, gRPC build) ───
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip build-essential \
      libglib2.0-0 libgl1 libstdc++6 libgomp1 ffmpeg \
      ca-certificates curl wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt

# ─── Create virtual environment ───
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# ─── Install Python dependencies with caching ───
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install \
    "numpy<2.0" apache-flink==1.19.0 \
    boto3 pyyaml opencv-python-headless \
    grpcio grpcio-tools requests Pillow minio kafka-python protobuf \
    google-cloud-storage \
    torch==2.2.2+cpu torchvision==0.17.2+cpu \
    onnx boxmot ffmpeg-python \
    --extra-index-url https://download.pytorch.org/whl/cpu



# ─── Copy application source ───
WORKDIR /opt/app
COPY agguard ./agguard
COPY configs ./configs

# ─── Compile gRPC stubs ───
RUN /opt/venv/bin/python -m grpc_tools.protoc \
      -I agguard/proto \
      --python_out=agguard/proto \
      --grpc_python_out=agguard/proto \
      agguard/proto/ingest.proto \
      agguard/proto/mask_classifier.proto \
      agguard/proto/mega_detector.proto

# ─── Patch imports in generated stubs ───
RUN /opt/venv/bin/python - <<'PY'
from pathlib import Path; import re
for p in Path("agguard/proto").glob("*_pb2_grpc.py"):
    s = p.read_text()
    s2 = re.sub(r'(?m)^import (\w+_pb2)\b', r'from . import \1', s)
    if s != s2:
        p.write_text(s2)
        print("✅ patched:", p)
PY


############################################################
# Stage 2 — Runtime image (Flink + PyFlink)
############################################################
FROM flink:1.19.3-scala_2.12-java11

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENCV_OPENCL_RUNTIME=disabled

# ─── Minimal runtime dependencies ───
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv libglib2.0-0 libgl1 libstdc++6 libgomp1 \
      ffmpeg ca-certificates curl wget && \
    rm -rf /var/lib/apt/lists/*

# ─── Copy prebuilt environment and app ───
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/app /opt/app

# ─── Environment variables for Flink + Python ───
ENV PATH="/opt/venv/bin:${PATH}" \
    PYFLINK_PYTHON=/opt/venv/bin/python \
    PYFLINK_CLIENT_EXECUTABLE=/opt/venv/bin/python \
    PYTHONPATH="/opt/app:/opt/venv/lib/python3.*/site-packages"

# ─── Kafka connectors (Flink 1.19) ───
RUN mkdir -p /opt/flink/lib && \
    wget -q --tries=5 --retry-connrefused --waitretry=5 \
      https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.7.0/kafka-clients-3.7.0.jar \
      -O /opt/flink/lib/kafka-clients-3.7.0.jar && \
    wget -q --tries=5 --retry-connrefused --waitretry=5 \
      https://repo1.maven.org/maven2/org/apache/flink/flink-connector-kafka/3.2.0-1.19/flink-connector-kafka-3.2.0-1.19.jar \
      -O /opt/flink/lib/flink-connector-kafka-3.2.0-1.19.jar

# ─── Runtime environment ───
ENV KAFKA_BROKERS=kafka:9092 \
    IN_TOPIC=dev-security-images-keys \
    OUT_TOPIC=alerts \
    PIPELINE_CFG=/opt/app/configs/default.yaml \
    PYTHONPATH=/opt/app \
    GRPC_HOST=security:50052

EXPOSE 50051

USER flink
WORKDIR /opt/app

CMD ["flink", "run", "-py", "agguard/pipeline/flink_job.py"]



