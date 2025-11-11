
FROM mcr.microsoft.com/devcontainers/python:1-3.10-bullseye
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgl1 libglib2.0-0 ffmpeg curl ca-certificates && \
#     rm -rf /var/lib/apt/lists/*
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgl1 libglib2.0-0 ffmpeg curl ca-certificates \
#     util-linux procps \
#  && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 ffmpeg curl ca-certificates \
    util-linux procps \
 && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --upgrade pip wheel setuptools

ENV AIRFLOW_VERSION=2.9.3
ENV PYTHON_VERSION=3.10
ENV CONSTRAINT_URL=https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" --constraint "${CONSTRAINT_URL}"

RUN pip install --no-cache-dir \
  "apache-airflow-providers-docker" \
  --constraint "${CONSTRAINT_URL}"


# === PyTorch CPU wheels ===
RUN pip install --no-cache-dir \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  torch==2.3.1+cpu torchvision==0.18.1+cpu torchaudio==2.3.1+cpu

# === YOLO===
RUN pip install --no-cache-dir \
  numpy==1.26.4 opencv-python-headless==4.9.0.80 ultralytics==8.2.10 \
  onnx==1.16.1 onnxruntime==1.18.1 \
  boto3 minio awscli requests tqdm

#root
RUN useradd -ms /bin/bash airflow
USER airflow
WORKDIR /opt/airflow
