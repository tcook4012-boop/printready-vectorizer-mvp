# app/main.py
import os
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.vectorizer.pipeline import vectorize_image

app = FastAPI(title="PrintReady Vectorizer API")

# --- CORS ---
# Allow your Vercel app and local dev
VERCEL_APP = os.getenv("VERCEL_FRONTEND", "https://printready-vectorizer-mvp.vercel.app")
origins = {
    VERCEL_APP,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(8),
    smoothness: Optional[str] = Form("medium"),
    primitive_snap: Optional[bool] = Form(False),
):
    """
    Vectorize an uploaded raster image via potrace and return raw SVG text.

    Multipart form fields expected by the frontend:
      - file: binary image
      - max_colors: int (palette reduction before thresholding)
      - smoothness: string (placeholder; compatibility only)
      - primitive_snap: bool (placeholder; compatibility only)
    """
    try:
        raw = await file.read()

        svg_text = vectorize_image(
            image_bytes=raw,
            max_colors=max_colors,
            smoothness=smoothness,
            primitive_snap=primitive_snap,
        )
        # Frontend expects {"svg": "<svg ...>"}
        return JSONResponse({"svg": svg_text})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
