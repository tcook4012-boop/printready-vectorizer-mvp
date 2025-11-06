# backend/app/Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000

# ✅ main.py is at the root of this WORKDIR, so the module is "main:app"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
