# app/main.py
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse, RedirectResponse
import os

# Our logo-safe pipeline (drop-in file you added at app/pipeline/logo_safe.py)
from app.pipeline.logo_safe import vectorize_logo_safe_to_svg_bytes

app = FastAPI(title="PrintReady Vectorizer API", version="0.1.0")

# ----- CORS -----
# Allow your frontend (Vercel) to call this API.
# You can set ALLOWED_ORIGINS in Render env (comma-separated) or just fall back to "*".
allowed = os.getenv("ALLOWED_ORIGINS", "*")
origins = [o.strip() for o in allowed.split(",")] if allowed else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----- Health/landing -----
@app.get("/")
def root():
    # Small landing + link to docs
    return {"ok": True, "service": "printready-vectorizer-api", "docs": "/docs"}

@app.get("/docs/")
def docs_redirect():
    # Nice-to-have: redirect /docs/ -> /docs
    return RedirectResponse(url="/docs")

# ----- Vectorize endpoint -----
@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(..., description="Raster to vectorize"),
    preset: str = Form(default="logo-safe", description="Pipeline preset (default: logo-safe)"),
):
    """
    Vectorizes a raster image to SVG.

    - Default preset: logo-safe (dehalo → quantize → clean → VTracer fills + Potrace strokes → compose)
    - Returns: SVG (image/svg+xml)
    """
    try:
        data = await file.read()

        # Only 'logo-safe' is implemented here. You can branch for other presets later.
        if preset in (None, "", "logo-safe"):
            svg_bytes = vectorize_logo_safe_to_svg_bytes(data)
            return Response(content=svg_bytes, media_type="image/svg+xml")

        raise HTTPException(status_code=400, detail=f"Unknown preset: {preset}")

    except HTTPException:
        raise
    except Exception as e:
        # Keep a compact, debuggable JSON error body for the frontend
        return JSONResponse(
            status_code=500,
            content={
                "error": "vectorization failed",
                "stderr": str(e),
                "cmd": ["vtracer", "potrace", "(logo-safe)"],
            },
        )
