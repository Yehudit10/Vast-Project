FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install PyQt6
RUN pip install PyQt6-WebEngine

COPY src/vast /app/src/vast
CMD ["python", "/app/src/vast/main.py"]
