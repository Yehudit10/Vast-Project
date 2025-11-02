FROM python:3.11-slim
ENV PIP_NO_CACHE_DIR=1 PIP_DEFAULT_TIMEOUT=1200 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir numpy==1.26.4 --only-binary=:all:


RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.1.2 torchvision==0.16.2 --only-binary=:all: --upgrade-strategy only-if-needed


COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt --only-binary=:all: --upgrade-strategy only-if-needed


COPY app.py model_registry.py /app/
COPY adapters /app/adapters
COPY models   /app/models

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
