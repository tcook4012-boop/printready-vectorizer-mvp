# /srv/app/main.py

import io
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

app = FastAPI(title="PrintReady Vectorizer (vtracer)")

# --- CORS (allow your Vercel frontend) ---
# Adjust/extend this list if you have other frontends.
ALLOWED_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "https://printready-vectorizer-mvp.vercel.app").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True, "service": "vectorizer", "engine": "vtracer"}


@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    # UI fields we currently map / partially ignore:
    max_colors: Optional[int] = Form(None),            # kept for compatibility, not sent to vtracer
    primitive_snap: Optional[bool] = Form(False),      # not supported in vtracer; ignored
    min_path_area_fraction: Optional[float] = Form(None),  # 0.0002 – 0.001 suggested from UI
    layer_order: Optional[str] = Form("light_to_dark"),    # UI only; ignored by vtracer
    smoothness: Optional[str] = Form("low"),               # UI only; ignored by vtracer
    # Optional: expose vtracer-native knob
    color_precision: Optional[float] = Form(None),     # if provided, passed to --color_precision
    mode: Optional[str] = Form("color"),               # vtracer modes: color | polygon | line
):
    """
    Accept an image upload, run `vtracer`, and return the SVG as text in JSON.
    """
    # Validate mode
    if mode not in {"color", "polygon", "line"}:
        raise HTTPException(status_code=400, detail=f"Unsupported mode '{mode}'")

    # Read binary content up front
    try:
        content = await file.read()
        if not content:
            raise ValueError("Empty file")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    tmp_dir = tempfile.mkdtemp(prefix="vtracer_")
    in_path = os.path.join(tmp_dir, "input")
    out_path = os.path.join(tmp_dir, "out.svg")

    # Deduce an extension for PIL friendliness (defaults to .png)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}:
        ext = ".png"
    in_path = in_path + ext

    try:
        # Save upload to disk
        with open(in_path, "wb") as f:
            f.write(content)

        # Get image dimensions for speckle filtering conversion
        try:
            with Image.open(io.BytesIO(content)) as im:
                width, height = im.size
        except Exception:
            # Fallback: open from disk if in-memory fails
            with Image.open(in_path) as im:
                width, height = im.size

        # Build vtracer command
        cmd = ["vtracer", "--mode", mode, "--input", in_path, "--output", out_path]

        # Optional: --color_precision (float). Lower values = fewer/stronger color merges.
        if color_precision is not None:
            try:
                # vtracer expects a float-ish number; we pass it through
                cp = float(color_precision)
                cmd += ["--color_precision", str(cp)]
            except Exception:
                # ignore bad value; keep defaults
                pass

        # Convert our "min_path_area_fraction (0–1)" -> pixel threshold for vtracer's speckle filter
        if min_path_area_fraction is not None:
            try:
                frac = float(min_path_area_fraction)
                if 0 < frac < 1:
                    px_thresh = max(1, int(frac * width * height))
                    cmd += ["--filter_speckle", str(px_thresh)]
            except Exception:
                # ignore bad value
                pass

        # Run vtracer
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=90,  # seconds
        )

        if proc.returncode != 0 or not os.path.exists(out_path):
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            detail = {
                "error": "vectorization failed",
                "stderr": stderr,
                "stdout": stdout,
                "cmd": cmd,
            }
            raise HTTPException(status_code=500, detail=detail)

        # Read SVG text
        with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
            svg_text = f.read()

        # Simple safety: ensure it's SVG
        if "<svg" not in svg_text.lower():
            raise HTTPException(status_code=500, detail="Output did not look like SVG")

        return {"svg": svg_text}

    finally:
        # Clean temp files
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
