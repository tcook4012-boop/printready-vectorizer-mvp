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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------ helpers ------------

SVG_START_RE = re.compile(r"<svg[\s>]", re.IGNORECASE)
SVG_END_RE = re.compile(r"</svg\s*>", re.IGNORECASE)

def extract_svg(raw: str) -> str:
    if not raw:
        raise ValueError("Empty output")
    m_start = SVG_START_RE.search(raw)
    if not m_start:
        raise ValueError("output is not an <svg> root")
    start = m_start.start()
    m_end = SVG_END_RE.search(raw, start)
    if m_end:
        return raw[start:m_end.end()].strip()
    return raw[start:].strip()

def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
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
    mode: str,               # "spline" | "polygon"
    color_precision: int,    # maps from maxColors
    corner_threshold: float, # e.g. 30
    filter_speckle: int,     # e.g. 4
) -> list[str]:
    """
    Match the flags your vtracer binary actually supports (per the error output):

      --color_precision <int>
      --corner_threshold <float>
      --filter_speckle <int>
      --input <path>
      --mode <spline|polygon>
      --output <path>
    """
    return [
        "vtracer",
        "--input", in_path,
        "--output", out_path,
        "--mode", mode,
        "--color_precision", str(int(color_precision)),
        "--corner_threshold", str(float(corner_threshold)),
        "--filter_speckle", str(int(filter_speckle)),
    ]

# ------------ routes ------------

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    maxColors: int = Form(...),
    smoothing: Optional[str] = Form("smooth"),     # "smooth" -> spline, "sharp" -> polygon
    cornerThreshold: Optional[float] = Form(30.0),
    filterSpeckle: Optional[int] = Form(4),
    thinLines: Optional[bool] = Form(False),       # accepted from UI but unused (not supported by your vtracer)
):
    tmpdir = tempfile.mkdtemp(prefix="vtracer_")
    in_path = os.path.join(tmpdir, "input")
    out_path = os.path.join(tmpdir, "out.svg")

    try:
        # save upload (keep extension for decoder)
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"]:
            ext = ".png"
        in_path = in_path + ext
        with open(in_path, "wb") as f:
            f.write(await file.read())

        mode = "spline" if (smoothing or "smooth").lower() == "smooth" else "polygon"
        color_precision = max(1, min(64, int(maxColors)))
        corner = float(cornerThreshold if cornerThreshold is not None else 30.0)
        speckle = int(filterSpeckle if filterSpeckle is not None else 4)

        cmd = build_vtracer_cmd(
            in_path,
            out_path,
            mode=mode,
            color_precision=color_precision,
            corner_threshold=corner,
            filter_speckle=speckle,
        )

        proc = run(cmd, timeout=180)

        if proc.returncode != 0 or not os.path.exists(out_path):
            # try to read any partial output for debugging
            snippet = ""
            if os.path.exists(out_path):
                try:
                    with open(out_path, "r", encoding="utf-8", errors="ignore") as fh:
                        snippet = fh.read(300)
                except Exception:
                    pass
            return JSONResponse(
                status_code=500,
                content={
                    "error": "vectorization failed",
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "cmd": cmd,
                    "snippet": snippet,
                },
            )

        with open(out_path, "r", encoding="utf-8", errors="ignore") as fh:
            raw = fh.read()

        svg = extract_svg(raw)
        return {"svg": svg}

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal error",
                "message": str(e),
                "trace": traceback.format_exc().splitlines()[-5:],
            },
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
