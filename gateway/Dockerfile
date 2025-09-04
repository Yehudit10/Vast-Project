# FROM python:3.11-slim

# ENV PYTHONDONTWRITEBYTECODE=1 \
#     PYTHONUNBUFFERED=1

# WORKDIR /app

# # 1) Install deps early for better Docker cache
# COPY gateway/requirements.txt /app/gateway/requirements.txt
# RUN pip install --no-cache-dir -r /app/gateway/requirements.txt

# # 2) Copy app code and proto schemas
# COPY gateway /app/gateway
# COPY proto   /app/proto

# # 3) Generate gRPC stubs into project root (/app) so imports are top-level: import query_pb2, query_pb2_grpc
# RUN python -m grpc_tools.protoc -I./proto \
#     --python_out=. --grpc_python_out=. \
#     ./proto/query.proto

# # 4) Runtime config
# ENV RUNNER_ADDR=runner:50051

# EXPOSE 8000
# CMD ["uvicorn", "gateway.gateway_main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# System CA + add NetFree certs
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY certs/*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates || true
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# Python deps
COPY gateway/requirements.txt /app/gateway/requirements.txt
RUN pip install --no-cache-dir -r /app/gateway/requirements.txt

# App code + proto
COPY gateway /app/gateway
COPY proto   /app/proto

# Generate stubs
RUN python -m grpc_tools.protoc -I./proto \
    --python_out=. --grpc_python_out=. \
    ./proto/query.proto

ENV RUNNER_ADDR=runner:50051
EXPOSE 8000
CMD ["uvicorn", "gateway.gateway_main:app", "--host", "0.0.0.0", "--port", "8000"]
