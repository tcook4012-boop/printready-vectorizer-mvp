# ---- Build stage: compile vtracer ----
FROM python:3.11-slim AS base
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates git pkg-config libssl-dev \
    rustc cargo \
    potrace imagemagick mkbitmap \
  && rm -rf /var/lib/apt/lists/*

RUN cargo install vtracer --version 0.6.5

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    potrace imagemagick mkbitmap \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app
COPY requirements.txt /srv/app/requirements.txt
RUN pip install --no-cache-dir -r /srv/app/requirements.txt

COPY --from=base /root/.cargo/bin/vtracer /usr/local/bin/vtracer
COPY app /srv/app/app

ENV PORT=8000
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

