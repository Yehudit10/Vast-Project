FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1) Install deps
COPY runner/requirements.txt /app/runner/requirements.txt
RUN pip install --no-cache-dir -r /app/runner/requirements.txt

# 2) Copy app code and proto schemas
COPY runner /app/runner
COPY proto  /app/proto

# 3) Generate gRPC stubs into project root (/app)
RUN python -m grpc_tools.protoc -I./proto \
    --python_out=. --grpc_python_out=. \
    ./proto/query.proto

# 4) Runtime config
ENV RUNNER_MODE=mock
# ENV FLINK_REST_URL=http://flink:8081

EXPOSE 50051
CMD ["python", "-m", "runner.runner_server"]
