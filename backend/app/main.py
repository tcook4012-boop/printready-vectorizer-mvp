# backend/app/main.py
import os
import re
import shutil
import tempfile
import traceback
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import subprocess

app = FastAPI()

# CORS: allow your web app to hit the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- helpers ----------

SVG_START_RE = re.compile(r"<svg[\s>]", re.IGNORECASE)
SVG_END_RE = re.compile(r"</svg\s*>", re.IGNORECASE)

def extract_svg(raw: str) -> str:
    """
    Accepts content that may include XML prolog / DOCTYPE / comments before <svg>.
    Returns the first <svg>…</svg> block (or <svg>…EOF if no end tag present).
    Raises ValueError if no <svg> tag found.
    """
    if not raw:
        raise ValueError("Empty output")
    m_start = SVG_START_RE.search(raw)
    if not m_start:
        raise ValueError("output is not an <svg> root")
    start = m_start.start()

    m_end = SVG_END_RE.search(raw, start)
    if m_end:
        end = m_end.end()
        return raw[start:end].strip()
    # If no closing tag, return from <svg> to end (some generators stream)
    return raw[start:].strip()

def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )

def build_vtracer_cmd(
    in_path: str,
    out_path: str,
    *,
    mode: str,
    max_colors: int,
    corner_threshold: float,
    filter_speckle: int,
    thin_lines: bool,
) -> list[str]:
    """
    vtracer 0.6.5 flags (tested):
      --mode <polygon|spline>
      -p, --palette-size <INT>        (colors)
      -c, --corner-threshold <FLOAT>  (e.g. 30)
      -f, --filter-speckle <INT>      (pixels)
      --thin-lines <true|false>

    We keep things minimal to reduce surface for parser errors.
    """
    cmd = [
        "vtracer",
        "--input", in_path,
        "--output", out_path,
        "--mode", mode,
        "-p", str(max_colors),
        "-c", str(corner_threshold),
        "-f", str(filter_speckle),
        "--thin-lines", "true" if thin_lines else "false",
    ]
    return cmd

# ---------- routes ----------

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    maxColors: int = Form(...),
    smoothing: Optional[str] = Form("smooth"),     # "smooth" | "sharp"
    cornerThreshold: Optional[float] = Form(30.0),
    filterSpeckle: Optional[int] = Form(4),
    thinLines: Optional[bool] = Form(False),
):
    """
    Accepts form-data:
      - file: image
      - maxColors: int
      - smoothing: "smooth"|"sharp" -> maps to vtracer mode
      - cornerThreshold: float
      - filterSpeckle: int
      - thinLines: bool
    Returns: {"svg": "<svg>...</svg>"} or 500 with stderr/cmd/snippet.
    """
    tmpdir = tempfile.mkdtemp(prefix="vtracer_")
    in_path = os.path.join(tmpdir, "input")
    out_path = os.path.join(tmpdir, "out.svg")

    try:
        # Save upload
        # Preserve extension for some decoders; fallback to .png
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"]:
            ext = ".png"
        in_path = in_path + ext

        with open(in_path, "wb") as f:
            f.write(await file.read())

        # Map smoothing -> mode
        mode = "spline" if (smoothing or "smooth").lower() == "smooth" else "polygon"

        # Defaults / guards
        max_colors = int(max(1, min(64, int(maxColors))))
        corner = float(cornerThreshold if cornerThreshold is not None else 30.0)
        speckle = int(filterSpeckle if filterSpeckle is not None else 4)
        thin = bool(thinLines)

        cmd = build_vtracer_cmd(
            in_path,
            out_path,
            mode=mode,
            max_colors=max_colors,
            corner_threshold=corner,
            filter_speckle=speckle,
            thin_lines=thin,
        )

        proc = run(cmd, timeout=180)

        # If vtracer failed (non-zero), surface detailed error + tiny snippet if any
        if proc.returncode != 0 or not os.path.exists(out_path):
            snippet = ""
            if os.path.exists(out_path):
                try:
                    with open(out_path, "r", encoding="utf-8", errors="ignore") as fh:
                        snippet = fh.read(300)
                except Exception:
                    snippet = ""
            return JSONResponse(
                status_code=500,
                content={
                    "error": "vectorization failed",
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "cmd": cmd,
                    "snippet": snippet[:400],
                },
            )

        # Read output and normalize to pure <svg>…</svg>
        with open(out_path, "r", encoding="utf-8", errors="ignore") as fh:
            raw = fh.read()

        svg = extract_svg(raw)
        return {"svg": svg}

    except Exception as e:
        # Unexpected error path
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal error",
                "message": str(e),
                "trace": traceback.format_exc().splitlines()[-5:],
            },
        )
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
