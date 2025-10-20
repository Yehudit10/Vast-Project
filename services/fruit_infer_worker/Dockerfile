FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# If your model needs system libs, add them (e.g., libgl1)
# RUN apt-get update && apt-get install -y libgl1 && rm -rf /var/lib/apt/lists/*
COPY worker.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "worker.py"]
