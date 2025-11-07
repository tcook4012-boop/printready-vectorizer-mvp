# backend/app/main.py
import os
import re
import shutil
import tempfile
import subprocess
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="PrintReady Vectorizer API", version="0.2.0")

# Allow frontend origins (adjust as you need)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Helpers
# ---------------------------

def _clean_svg(svg: str) -> str:
    """Strip BOM, XML prolog, and DOCTYPE to keep the frontend normalizer happy."""
    svg = svg.lstrip("\ufeff")
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg, flags=re.I)
    svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg, flags=re.I)
    return svg.strip()

def _looks_like_svg_root(s: str) -> bool:
    return bool(re.match(r"^\s*<\s*svg[\s>]", s, flags=re.I))

def _safe_bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"1", "true", "yes", "on"}

def _clamp_int(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))

def _to_float(val: Optional[str], default: float) -> float:
    if val is None or str(val).strip() == "":
        return default
    try:
        return float(val)
    except Exception:
        return default

def _to_int(val: Optional[str], default: int) -> int:
    if val is None or str(val).strip() == "":
        return default
    try:
        return int(val)
    except Exception:
        return default

def build_vtracer_cmd(
    in_path: str,
    out_path: str,
    *,
    curve_mode: str,          # "spline" or "polygon"
    color_precision: int,     # integer; vtracer expects --color_precision
    corner_threshold: float,  # numeric
    filter_speckle: int,      # integer
    segment_length: float,    # numeric
    splice_threshold: float,  # numeric
    hierarchical: str,        # "stacked" or "none"
    thin_lines: bool,         # True/False
) -> list[str]:
    """
    vtracer 0.6.5 expects:
      --mode <spline|polygon>
      --input <file>
      --output <file>
      --color_precision <int>
      --corner_threshold <float>
      --filter_speckle <int>
      --segment_length <float>
      --splice_threshold <float>
      --hierarchical <stacked|none>
      --thin_lines <true|false>
    Short flags also exist (-p, -c, -f, -l, -s), but we’ll be explicit for clarity.
    """
    vtracer_bin = os.environ.get("VTRACER_PATH", "vtracer")

    cmd = [
        vtracer_bin,
        "--input", in_path,
        "--output", out_path,
        "--mode", curve_mode,
        "--color_precision", str(color_precision),
        "--corner_threshold", str(corner_threshold),
        "--filter_speckle", str(filter_speckle),
        "--segment_length", str(segment_length),
        "--splice_threshold", str(splice_threshold),
        "--hierarchical", hierarchical,
        "--thin_lines", "true" if thin_lines else "false",
    ]

    return cmd

# ---------------------------
# Routes
# ---------------------------

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    # UI / form fields (all optional except file)
    maxColors: Optional[int] = Form(None),
    smoothing: Optional[str] = Form(None),          # "smooth" | "sharp"
    primitiveSnap: Optional[str] = Form(None),      # "true"/"false"
    cornerThreshold: Optional[str] = Form(None),    # numeric string (pixels/angle-ish)
    filterSpeckle: Optional[str] = Form(None),      # integer string
    thinLines: Optional[str] = Form(None),          # "true"/"false"
):
    """
    Maps UI options to vtracer CLI (0.6.5) flags correctly.
    - We use `--mode spline|polygon` (curve fit), NOT "color" (which was a previous mistake).
    - We map `maxColors` -> `--color_precision` (clamped 1..64; typical values 2..16).
    - We sanitize numerics and provide robust defaults.
    """

    # Validate vtracer exists
    vtracer_path = shutil.which(os.environ.get("VTRACER_PATH", "vtracer"))
    if not vtracer_path:
        return JSONResponse(
            status_code=500,
            content={"error": "vtracer not found on PATH. Ensure it's installed in the container."},
        )

    # Read upload → temp files
    tmpdir = tempfile.mkdtemp(prefix="vtrace_")
    in_path = os.path.join(tmpdir, "input.png")
    out_path = os.path.join(tmpdir, "output.svg")

    try:
        # Save input file
        with open(in_path, "wb") as f:
            f.write(await file.read())

        # -------- Parameter mapping / defaults --------
        # color precision: quality vs. color richness; clamp to something safe
        # If maxColors is not provided, pick 8 as a reasonable default
        color_precision = _clamp_int(int(maxColors) if maxColors is not None else 8, 1, 64)

        # smoothing: "smooth" => spline (curvy), anything else => polygon (sharper corners)
        curve_mode = "spline" if (smoothing or "").strip().lower() == "smooth" else "polygon"

        # vtracer numeric params — choose logo-friendly defaults
        corner_threshold = _to_float(cornerThreshold, 10.0)   # was causing “not numeric” if given like "0.05"
        filter_speckle  = _to_int(filterSpeckle, 4)           # remove tiny blobs
        segment_length  = 3.0                                  # smaller -> smoother curves / more points
        splice_threshold = 5.0                                 # helps reduce micro-corners / joins
        hierarchical = "stacked"                               # stack overlapping shapes for logos
        thin_lines_flag = _safe_bool(thinLines, False)

        # primitiveSnap isn’t a vtracer flag; we ignore it here (you can use it upstream to pre-clean the raster)

        # -------- Build & run command --------
        cmd = build_vtracer_cmd(
            in_path,
            out_path,
            curve_mode=curve_mode,
            color_precision=color_precision,
            corner_threshold=corner_threshold,
            filter_speckle=filter_speckle,
            segment_length=segment_length,
            splice_threshold=splice_threshold,
            hierarchical=hierarchical,
            thin_lines=thin_lines_flag,
        )

        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if proc.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "vectorization failed",
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "cmd": cmd,
                },
            )

        if not os.path.exists(out_path):
            return JSONResponse(
                status_code=500,
                content={"error": "vectorization failed: no output produced", "cmd": cmd},
            )

        with open(out_path, "r", encoding="utf-8", errors="replace") as fh:
            svg_data = fh.read()

        svg_data = _clean_svg(svg_data)

        if not _looks_like_svg_root(svg_data):
            return JSONResponse(
                status_code=500,
                content={
                    "error": "vectorization succeeded but output is not an <svg> root",
                    "snippet": svg_data[:200],
                },
            )

        return {"svg": svg_data}

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"exception during vectorization: {e.__class__.__name__}: {e}"},
        )
    finally:
        # Clean temp dir
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


# For local debugging: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
