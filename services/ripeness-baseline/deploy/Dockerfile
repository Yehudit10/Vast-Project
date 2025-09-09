FROM python:3.11-slim
WORKDIR /app

# שכבת תלויות
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# קוד + SQL + דוגמאות
COPY src/ ./src/
COPY deploy/sql/ ./deploy/sql/
COPY samples/ ./samples/

ENV PYTHONPATH=/app/src
ENV SAMPLES_DIR=/app/samples
ENV FRUIT_TYPE=apple

CMD ["python","-u","/app/src/main.py"]
