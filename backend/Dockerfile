# ---- Stage 1: build tools (install vtracer) -------------------------------
FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates git \
    pkg-config libssl-dev \
    rustc cargo \
    inkscape potrace \
 && rm -rf /var/lib/apt/lists/*

# Install vtracer
RUN cargo install vtracer

# ---- Stage 2: runtime ------------------------------------------------------
FROM python:3.11-slim

# Runtime deps for engines
RUN apt-get update && apt-get install -y --no-install-recommends \
    inkscape potrace \
 && rm -rf /var/lib/apt/lists/*

# Copy vtracer binary from build stage
COPY --from=base /root/.cargo/bin/vtracer /usr/local/bin/vtracer

# Working dir for app
WORKDIR /srv/app

# IMPORTANT: paths are relative to the build context (Root Directory = backend)
COPY requirements.txt /srv/app/requirements.txt
RUN pip install --no-cache-dir -r /srv/app/requirements.txt

# Copy FastAPI app code
COPY app /srv/app

ENV PORT=8000
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
