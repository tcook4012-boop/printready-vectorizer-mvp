FROM python:3.11-slim

# System deps needed for OpenCV
RUN apt-get update && apt-get install -y \
    ffmpeg libsm6 libxext6 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# Expose default port
EXPOSE 8000

# Run Uvicorn and bind to Render's assigned port
CMD ["bash","-lc","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
