# backend/Dockerfile
FROM python:3.11-slim

# Minimal system deps used by opencv-headless wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# We'll keep our code under /srv
WORKDIR /srv

# Install Python deps
COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

# Copy the backend app package
COPY app/ /srv/app/

# (optional but nice) ensure Python can import from /srv
ENV PYTHONPATH=/srv
ENV PORT=8000

# 🔑 main.py is inside the app package → module path is app.main:app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
