# PrintReady Vectorizer — MVP (No Third-Party Tracer)

This is a **first-party vectorization engine** with a simple web UI. It does **not** call Potrace/VTracer or any external tracer. It uses a deterministic, classical-geometry pipeline.

## What you get
- **Backend (FastAPI, Python)**: `/vectorize` endpoint that converts a PNG/JPG into **SVG** using a custom pipeline: color clustering, contour extraction, adaptive RDP simplification, primitive snapping (lines/circles), and cubic Bézier fitting.
- **Frontend (Next.js/React)**: drag‑and‑drop uploader, live preview, basic controls (max colors, smoothness, primitive snap, HQ refine placeholder).
- **No external tracer** — entirely your own code.

> This MVP is designed for logos/flat artwork. It will already outperform naive threshold tracers on corners/lines. We’ll iterate for photo‑like images later.

---

## Quick Start (non‑technical)

### Option A: One‑line dev run (Docker)
1) Install Docker Desktop.
2) In a terminal from the project folder, run:
```
docker compose up --build
```
3) Open the web app: http://localhost:3000

### Option B: Manual (Mac/Windows)
**Backend**
1) Install Python 3.10+
2) Create venv and install deps:
```
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
3) Run the API:
```
uvicorn app.main:app --reload --port 8000
```

**Frontend**
1) Install Node.js 18+
2) In another terminal:
```
cd frontend
npm install
npm run dev
```
3) Open http://localhost:3000

---

## How it works (high level)
1) **Palette**: Convert to Lab, reduce colors via k‑means with ΔE (CIEDE2000) distance.
2) **Edges/Contours**: Sobel + non‑max suppression (simple Canny‑like), contour tracing (Moore neighbor).
3) **Simplify**: Ramer–Douglas–Peucker (adaptive epsilon by curvature).
4) **Primitive snapping**: straight lines (least squares) + circles (Kasa/Pratt fit) when confidence is high.
5) **Bézier fitting**: cubic segments with C¹ continuity on “smooth” joints; preserve “cusp” corners.
6) **SVG export**: closed paths, optional stroke→outline.

> No ML is required to run. Later we can add a small helper model to improve corner tagging.

---

## Roadmap
- Add ellipse/arc snapping and rounded‑rect inference.
- Add optional differentiable refinement pass (diffvg) for “HQ” mode.
- DXF/EPS/PDF exporters (SVG is included now).
- Stripe paywall and job queue for batch conversion.

---

## Files
- `backend/app/main.py` — FastAPI routes
- `backend/app/vectorizer/` — the vectorization engine (pure Python + NumPy)
- `frontend/` — Next.js app (upload UI, preview)
- `docker-compose.yml` — one‑command dev setup

---

## Support
This repo is designed so you can run it without technical background. If anything is confusing, open `README.md` and follow steps exactly.
