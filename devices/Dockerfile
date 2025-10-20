# # syntax=docker/dockerfile:1
# FROM python:3.12-slim

# RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
#     rm -rf /var/lib/apt/lists/*

# RUN pip install paho-mqtt

# WORKDIR /app
# COPY drone_publisher.py .

# ENV IMAGES_DIR=/data/images
# ENV META_DIR=/data/metadata
# ENV MQTT_HOST=large-mosquitto
# ENV MQTT_PORT=1885
# ENV MQTT_TOPIC=MQTT/imagery/new
# ENV CAMERA_ID=drone-01
# ENV INTERVAL_CHECK=180
# ENV INTERVAL_PUBLISH=60
# ENV MQTT_QOS=1

# CMD ["python", "-u", "/app/drone_publisher.py"]


# syntax=docker/dockerfile:1
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN pip install paho-mqtt

WORKDIR /app
COPY drone_publisher.py .

CMD ["python", "-u", "/app/drone_publisher.py"]
