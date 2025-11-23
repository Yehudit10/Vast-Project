FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install basic dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-0 libgl1 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Copy app
WORKDIR /app
COPY agguard/app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agguard ./agguard
COPY configs ./configs

EXPOSE 8080
HEALTHCHECK CMD curl -f http://localhost:8080/ || exit 1

CMD ["uvicorn", "agguard.app.media_proxy:app", "--host", "0.0.0.0", "--port", "8080"]
