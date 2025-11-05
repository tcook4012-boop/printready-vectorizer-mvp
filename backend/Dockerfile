# Dockerfile
FROM python:3.11-slim

# System deps: potrace + build essentials for Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    potrace \
    libjpeg62-turbo-dev zlib1g-dev libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app ./app

# Expose and run
ENV PORT=8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
