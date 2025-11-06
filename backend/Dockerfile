# --- Stage 1: Build tools (to install vtracer) -------------------------------
FROM python:3.11-slim AS base

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates git \
    pkg-config libssl-dev \
    rustc cargo \
    inkscape potrace \
 && rm -rf /var/lib/apt/lists/*

# Install vtracer via cargo (deterministic, no GUI needed)
# If you want to pin a version, add:  cargo install vtracer --version 0.6.0
RUN cargo install vtracer

# --- Stage 2: App ------------------------------------------------------------
FROM python:3.11-slim

# Runtime tools needed by our app
RUN apt-get update && apt-get install -y --no-install-recommends \
    inkscape potrace \
 && rm -rf /var/lib/apt/lists/*

# Copy vtracer binary from the build stage
COPY --from=base /root/.cargo/bin/vtracer /usr/local/bin/vtracer

# App files
WORKDIR /srv/app
COPY backend/requirements.txt /srv/app/requirements.txt
RUN pip install --no-cache-dir -r /srv/app/requirements.txt

# Copy app code
COPY backend/app /srv/app

# Render/uvicorn
ENV PORT=8000
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
