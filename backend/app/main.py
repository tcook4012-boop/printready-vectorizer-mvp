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

# Allow your Vercel frontend (comma-separate to add more)
ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "https://printready-vectorizer-mvp.vercel.app",
).split(",")

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

    # UI compatibility fields (some are ignored by vtracer)
    max_colors: Optional[int] = Form(None),                 # ignored by vtracer (we may map later)
    primitive_snap: Optional[bool] = Form(False),           # ignored
    min_path_area_fraction: Optional[float] = Form(None),   # 0.0002–0.001 suggested
    layer_order: Optional[str] = Form("light_to_dark"),     # ignored
    smoothness: Optional[str] = Form("low"),                # ignored

    # vtracer-native knobs
    color_precision: Optional[float] = Form(None),          # passed to --color_precision (optional)
    mode: Optional[str] = Form("spline"),                   # vtracer: spline | polygon
):
    # Normalize/validate mode (map any legacy 'color' to 'spline')
    normalized_mode = (mode or "spline").strip().lower()
    if normalized_mode not in {"spline", "polygon"}:
        normalized_mode = "spline"

    # Load upload
    try:
        content = await file.read()
        if not content:
            raise ValueError("Empty file")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    tmp_dir = tempfile.mkdtemp(prefix="vtracer_")
    in_path = os.path.join(tmp_dir, "input")
    out_path = os.path.join(tmp_dir, "out.svg")

    # Choose an extension PIL understands
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}:
        ext = ".png"
    in_path = in_path + ext

    try:
        with open(in_path, "wb") as f:
            f.write(content)

        # Get image size for speckle-pixel conversion
        try:
            with Image.open(io.BytesIO(content)) as im:
                width, height = im.size
        except Exception:
            with Image.open(in_path) as im:
                width, height = im.size

        # Build vtracer command
        cmd = ["vtracer", "--mode", normalized_mode, "--input", in_path, "--output", out_path]

        # Optional: color_precision
        if color_precision is not None:
            try:
                cp = float(color_precision)
                cmd += ["--color_precision", str(cp)]
            except Exception:
                pass  # ignore bad values

        # Speckle filtering: fraction → pixel count
        if min_path_area_fraction is not None:
            try:
                frac = float(min_path_area_fraction)
                if 0 < frac < 1:
                    px_thresh = max(1, int(frac * width * height))
                    cmd += ["--filter_speckle", str(px_thresh)]
            except Exception:
                pass

        # Run
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=90
        )

        if proc.returncode != 0 or not os.path.exists(out_path):
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "vectorization failed",
                    "stderr": (proc.stderr or "").strip(),
                    "stdout": (proc.stdout or "").strip(),
                    "cmd": cmd,
                },
            )

        with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
            svg_text = f.read()

        if "<svg" not in svg_text.lower():
            raise HTTPException(status_code=500, detail="Output did not look like SVG")

        return {"svg": svg_text}

    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
