FROM python:3.11-slim

# System deps for OpenCV + Potrace
RUN apt-get update && apt-get install -y \
    potrace \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# If you want HEAD on /health to not 405, make sure main.py handles HEAD too.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
