FROM python:3.11-slim

# --- System setup ---
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC

# --- Dependencies ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- App ---
COPY . .


# --- Default command ---
CMD ["python", "-u", "app.py"]
