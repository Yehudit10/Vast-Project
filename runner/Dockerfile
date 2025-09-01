# FROM python:3.11-slim

# ENV PYTHONDONTWRITEBYTECODE=1 \
#     PYTHONUNBUFFERED=1

# WORKDIR /app

# # # 1) Install deps
# COPY runner/requirements.txt /app/runner/requirements.txt
# RUN pip install --no-cache-dir -r /app/runner/requirements.txt

# # 2) Copy app code and proto schemas
# COPY runner /app/runner
# COPY proto  /app/proto

# # 3) Generate gRPC stubs into project root (/app)
# RUN python -m grpc_tools.protoc -I./proto \
#     --python_out=. --grpc_python_out=. \
#     ./proto/query.proto

# # 4) Runtime config
# ENV RUNNER_MODE=mock
# ENV FLINK_REST_URL=http://flink:8081

# EXPOSE 50051
# CMD ["python", "-m", "runner.runner_server"]
# runner/Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1) Install Python deps used by the runner (grpc, grpc-tools for protoc)
COPY runner/requirements.txt /app/runner/requirements.txt
RUN pip install --no-cache-dir -r /app/runner/requirements.txt

# 2) Copy code: runner, DSL package, and proto schema
COPY runner /app/runner
COPY dsl    /app/dsl
COPY proto  /app/proto

# 3) Generate gRPC stubs into project root (/app)
RUN python -m grpc_tools.protoc -I./proto \
    --python_out=. --grpc_python_out=. \
    ./proto/query.proto

# 4) Runtime env (SQLite by default; compose will mount /data/app.db)
ENV RUNNER_MODE=real \
    SQLITE_DB=/data/app.db \
    LOG_LEVEL=INFO \
    PYTHONPATH=/app

EXPOSE 50051
CMD ["python", "runner/runner_server.py"]

