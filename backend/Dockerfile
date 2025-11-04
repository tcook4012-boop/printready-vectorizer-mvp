# Dockerfile
FROM python:3.11-slim

# Install potrace (needed by the pipeline) and clean up
RUN apt-get update && apt-get install -y --no-install-recommends \
    potrace \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app ./app

ENV PORT=8000
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
