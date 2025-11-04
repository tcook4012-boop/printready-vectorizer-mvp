# ---- Base Python image ----
FROM python:3.11-slim

# ---- Install system dependencies, including potrace ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    potrace \
    && rm -rf /var/lib/apt/lists/*

# ---- Set working directory ----
WORKDIR /app

# ---- Install Python dependencies ----
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# ---- Copy the rest of the app code ----
COPY . .

# ---- Expose port for Render ----
ENV PORT=8000

# ---- Start server ----
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
