
FROM python:3.12-slim
WORKDIR /app
RUN pip install psycopg2-binary
COPY generator.py /app/generator.py
CMD ["python", "generator.py"]
