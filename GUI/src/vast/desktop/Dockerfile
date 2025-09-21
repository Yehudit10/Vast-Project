# FROM python:3.11-slim
# WORKDIR /app


# COPY requirements.txt /app/requirements.txt
# RUN pip install --no-cache-dir -r requirements.txt
# RUN pip install PyQt6
# RUN pip install PyQt6-WebEngine

# COPY src/vast /app/src/vast
# CMD ["python", "/app/src/vast/main.py"]
FROM python:3.11-slim

WORKDIR /app

# התקנת ספריות מערכת מינימליות להרצת PyQt6-WebEngine
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxext6 \
    libxi6 \
    libxrender1 \
    libdbus-1-3 \
    libfontconfig1 \
    libfreetype6 \
    libxcb1 \
    libxkbcommon0 \
    libnss3 \
    libnspr4 \
    libsm6 \
    libxrandr2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libgbm1 \
    libxdamage1 \
    libxfixes3 \
    && rm -rf /var/lib/apt/lists/*


# התקנת חבילות Python
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir PyQt6 PyQt6-WebEngine

# העתקת קוד המקור
COPY src/vast /app/src/vast

# הפעלה של הקובץ הראשי
CMD ["python", "/app/src/vast/main.py"]
