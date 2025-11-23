FROM python:3.11-slim
RUN pip install --no-cache-dir confluent-kafka psycopg2-binary
WORKDIR /app
COPY fruit_defect_sink.py ./
CMD ["python","-u","fruit_defect_sink.py"]
