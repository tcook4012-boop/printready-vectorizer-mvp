# backend/Dockerfile
FROM python:3.11-slim

# System libs some wheels need at runtime (OpenCV, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Render sets $PORT; default to 8000 locally
ENV PORT=8000

# IMPORTANT: your entrypoint module lives at app/vectorizer/main.py
CMD ["uvicorn", "app.vectorizer.main:app", "--host", "0.0.0.0", "--port", "8000"]
