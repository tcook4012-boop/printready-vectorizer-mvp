# ---- Build stage: compile vtracer and mkbitmap (optional but recommended) ----
FROM python:3.11-slim AS base

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates git pkg-config libssl-dev \
    rustc cargo \
    potrace imagemagick \
    autoconf automake libtool \
  && rm -rf /var/lib/apt/lists/*

# vtracer (Rust)
RUN cargo install vtracer --version 0.6.5

# mkbitmap (prefilter for potrace; improves smoothness on mono logos)
# If this ever fails on your image, you can comment this block out — the API will still run.
RUN git clone https://github.com/hodefoting/mkbitmap.git /tmp/mkbitmap \
 && cd /tmp/mkbitmap && ./autogen.sh && ./configure && make && make install

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    potrace imagemagick \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

# ✅ paths are relative to /backend (no "backend/" prefix!)
COPY requirements.txt /srv/app/requirements.txt
RUN pip install --no-cache-dir -r /srv/app/requirements.txt

# Bring vtracer and mkbitmap from builder
COPY --from=base /root/.cargo/bin/vtracer /usr/local/bin/vtracer
COPY --from=base /usr/local/bin/mkbitmap /usr/local/bin/mkbitmap

# App code (expects /srv/app/app/main.py with FastAPI instance named `app`)
COPY app /srv/app/app

ENV PORT=8000
EXPOSE 8000

# NOTE: module path must match folder layout (app/main.py ⇒ app.main:app)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
