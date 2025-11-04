FROM python:3.11-slim

# System deps (potrace + minimal libs some wheels probe for)
RUN apt-get update && apt-get install -y --no-install-recommends \
    potrace \
    libglib2.0-0 \
    libgl1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Make sure we get the headless OpenCV wheel and stable resolver behavior
COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# App code
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
