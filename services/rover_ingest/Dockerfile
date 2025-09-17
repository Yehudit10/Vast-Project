FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

COPY services/rover_ingest/requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt


COPY . /app
EXPOSE 9109
CMD ["python", "-m", "services.rover_ingest.app"]
