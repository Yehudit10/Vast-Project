FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# copy code
COPY configs ./configs
COPY models ./models
COPY training ./training
COPY inference ./inference
# Copy model artifact at build time if already exists (optional)
COPY ripeness_mobilenet_v3.onnx ./ripeness_mobilenet_v3.onnx

EXPOSE 8080
CMD ["uvicorn", "inference.app:app", "--host", "0.0.0.0", "--port", "8080"]
