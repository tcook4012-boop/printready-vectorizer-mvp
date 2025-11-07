FROM python:3.11-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates git \
    pkg-config libssl-dev rustc cargo inkscape potrace \
  && rm -rf /var/lib/apt/lists/*
RUN cargo install vtracer

FROM python:3.11-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    inkscape potrace \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

# ✅ paths are relative to /backend (no "backend/" prefix!)
COPY requirements.txt /srv/app/requirements.txt
RUN pip install --no-cache-dir -r /srv/app/requirements.txt

COPY --from=base /root/.cargo/bin/vtracer /usr/local/bin/vtracer
COPY app /srv/app

ENV PORT=8000
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

