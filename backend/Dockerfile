# ---------- base stage: build vtracer ----------
FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates git \
    pkg-config libssl-dev \
    rustc cargo \
    inkscape potrace \
  && rm -rf /var/lib/apt/lists/*

# Build/install vtracer (Rust CLI)
RUN cargo install vtracer

# ---------- runtime stage ----------
FROM python:3.11-slim AS runtime

# OS deps for potrace/inkscape runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    inkscape potrace \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

# IMPORTANT: paths are now relative to /backend (Root Directory)
COPY requirements.txt /srv/app/requirements.txt
RUN pip install --no-cache-dir -r /srv/app/requirements.txt

# Copy vtracer binary from base
COPY --from=base /root/.cargo/bin/vtracer /usr/local/bin/vtracer

# Copy app code
COPY app /srv/app

# For Render
ENV PORT=8000
EXPOSE 8000

# If you're using FastAPI:
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
