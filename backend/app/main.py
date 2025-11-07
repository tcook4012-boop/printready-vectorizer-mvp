# backend/app/main.py
import io
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image

app = FastAPI()


def build_vtracer_cmd(
    input_path: str,
    output_path: str,
    *,
    mode: str,                 # "spline" or "polygon"
    color_precision: int,      # integer (vtracer expects int)
    corner_threshold: int,     # integer (vtracer expects int)
    filter_speckle: int,       # integer (vtracer expects int)
    segment_length: float = 3.0,
    splice_threshold: float = 5.0,
    hierarchical: str = "stacked",
) -> list[str]:
    """
    vtracer 0.6.5 flags (accepted):
      --input <path> --output <path> --mode <spline|polygon>
      --color_precision <int>
      --corner_threshold <int>
      --filter_speckle <int>
      --segment_length <float>
      --splice_threshold <float>
      --hierarchical <none|stacked>
    """
    return [
        "vtracer",
        "--input", input_path,
        "--output", output_path,
        "--mode", mode,
        "--color_precision", str(int(color_precision)),
        "--corner_threshold", str(int(corner_threshold)),
        "--filter_speckle", str(int(filter_speckle)),
        "--segment_length", str(float(segment_length)),
        "--splice_threshold", str(float(splice_threshold)),
        "--hierarchical", hierarchical,
    ]


def normalize_image_to_png(tmp_dir: str, upload: UploadFile) -> str:
    """
    Ensure we feed vtracer a solid PNG/JPG. Convert anything else to PNG.
    """
    raw = upload.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file upload")

    try:
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGBA")
    except Exception:
        # If PIL can't open it, just write the raw bytes to jpg and let vtracer fail loudly.
        tmp_fallback = os.path.join(tmp_dir, "input.jpg")
        with open(tmp_fallback, "wb") as f:
            f.write(raw)
        return tmp_fallback

    out_path = os.path.join(tmp_dir, "input.png")
    img.save(out_path, format="PNG")
    return out_path


def read_svg_or_raise(svg_path: str) -> str:
    if not os.path.exists(svg_path):
        raise HTTPException(status_code=500, detail={"error": "no svg produced"})
    try:
        # Do NOT strip — keep content as-is. Just basic sanity checks.
        with open(svg_path, "r", encoding="utf-8", errors="replace") as f:
            svg = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": f"failed to read svg: {e}"})

    # Basic validation: must contain a root <svg ...>
    if not svg or ("<svg" not in svg.lower()):
        snippet = svg[:200] if svg else ""
        raise HTTPException(
            status_code=500,
            detail={"error": "output is not an <svg> root", "snippet": snippet},
        )
    return svg


@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    # UI params (strings/booleans come from form-data):
    maxColors: int = Form(4),                     # maps to color_precision
    smoothing: Optional[str] = Form("smooth"),    # "smooth"|"sharp" => spline|polygon
    primitiveSnap: Optional[bool] = Form(False),  # unused by vtracer; kept for API compat
    cornerThreshold: Optional[str] = Form("30"),  # MUST be integer for vtracer
    filterSpeckle: Optional[str] = Form("4"),     # MUST be integer
) -> JSONResponse:
    """
    Accepts an image, runs vtracer 0.6.5 with stable flags, returns raw SVG text.
    """
    # Map UI smoothing -> vtracer mode
    mode = "spline" if (smoothing or "").lower().strip() == "smooth" else "polygon"

    # Coerce numeric strings into correct types vtracer expects
    try:
        color_precision = int(maxColors)
    except Exception:
        color_precision = 4

    try:
        corner_threshold = int(float(cornerThreshold or "30"))
    except Exception:
        corner_threshold = 30

    try:
        filter_speckle = int(float(filterSpeckle or "4"))
    except Exception:
        filter_speckle = 4

    # Temporary working dir
    tmp_dir = tempfile.mkdtemp(prefix="vtracer_")
    input_path = ""
    output_path = os.path.join(tmp_dir, "out.svg")

    try:
        # Normalize to PNG input
        input_path = normalize_image_to_png(tmp_dir, file)

        # Build and run command
        cmd = build_vtracer_cmd(
            input_path,
            output_path,
            mode=mode,
            color_precision=color_precision,
            corner_threshold=corner_threshold,
            filter_speckle=filter_speckle,
            segment_length=3.0,
            splice_threshold=5.0,
            hierarchical="stacked",
        )

        run = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if run.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "vectorization failed",
                    "stdout": run.stdout,
                    "stderr": run.stderr,
                    "cmd": cmd,
                },
            )

        svg = read_svg_or_raise(output_path)

        # Return raw SVG string in JSON
        return JSONResponse({"svg": svg})

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
