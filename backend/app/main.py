import os
import shutil
import subprocess
import tempfile
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# -------------------------------------------------
# App + CORS (allow the Vercel frontend)
# -------------------------------------------------
app = FastAPI(title="PrintReady Vectorizer API")

# Keep it open for now (simple + reliable). If you want to restrict later,
# replace ["*"] with ["https://printready-vectorizer-mvp.vercel.app", "http://localhost:3000"].
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# Utilities
# -------------------------------------------------
def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)

def _exists_nonempty(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0

def _which(name: str) -> Optional[str]:
    return shutil.which(name)

def _have(name: str) -> bool:
    return _which(name) is not None

def _clean(paths: List[str]):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except:
            pass

def _save_upload(upload: UploadFile, suffix: str = ".jpg") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as tmp:
        shutil.copyfileobj(upload.file, tmp)
        tmp.flush()
        os.fsync(tmp.fileno())
    return path

# -------------------------------------------------
# Engines
# -------------------------------------------------
def vtracer_cmd(inp: str, outp: str, *, mode: str, max_colors: int, corner_threshold: float, filter_speckle: int) -> List[str]:
    return [
        "vtracer",
        "--input", inp,
        "--output", outp,
        "--mode", mode,  # "polygon" or "spline"
        "--color_precision", str(max_colors),
        "--corner_threshold", str(int(corner_threshold)),
        "--filter_speckle", str(int(filter_speckle)),
    ]

def _imagemagick_bin() -> Optional[str]:
    # IM7 commonly ships as "magick", but Debian also gives "convert" via alternatives
    if _have("magick"):
        return "magick"
    if _have("convert"):
        return "convert"
    return None

def _to_pgm_with_imagemagick(inp: str, out_pgm: str, threshold: Optional[int]) -> subprocess.CompletedProcess:
    im = _imagemagick_bin()
    if not im:
        # no ImageMagick — tell caller we couldn't run
        return subprocess.CompletedProcess(args=["convert"], returncode=127, stdout="", stderr="ImageMagick not found")

    # Use Otsu automatically unless an explicit threshold (0..100) is provided
    if threshold is None:
        # Auto-threshold (Otsu) → grayscale → PGM
        cmd = [im, inp, "-colorspace", "Gray", "-auto-threshold", "Otsu", out_pgm]
    else:
        # Explicit % threshold
        cmd = [im, inp, "-colorspace", "Gray", "-threshold", f"{threshold}%", out_pgm]

    return _run(cmd)

def potrace_pipeline(inp: str, out_svg: str, threshold: Optional[int]) -> subprocess.CompletedProcess:
    """
    JPG/PNG → (IM) PGM → (optional mkbitmap smoothing) → Potrace → SVG
    """
    pgm = tempfile.mktemp(suffix=".pgm")
    smoothed = None

    try:
        # Step 1: raster → PGM
        proc_conv = _to_pgm_with_imagemagick(inp, pgm, threshold)
        if proc_conv.returncode != 0 or not _exists_nonempty(pgm):
            return subprocess.CompletedProcess(args=["convert"], returncode=1, stdout=proc_conv.stdout,
                                              stderr=f"IM conversion failed: {proc_conv.stderr}")

        # Step 2 (optional): mkbitmap smoothing/feathering
        work_pgm = pgm
        if _have("mkbitmap"):
            smoothed = tempfile.mktemp(suffix=".pgm")
            # -f 4 (feather), -s 2 (smooth) are good defaults for logo scans
            proc_mkb = _run(["mkbitmap", "-f", "4", "-s", "2", "-o", smoothed, pgm])
            if proc_mkb.returncode == 0 and _exists_nonempty(smoothed):
                work_pgm = smoothed  # use the smoothed version

        # Step 3: potrace → SVG
        return _run(["potrace", "-s", "-o", out_svg, work_pgm])

    finally:
        _clean([pgm, smoothed] if smoothed else [pgm])

def choose_engine(engine: str, max_colors: int, smoothing: str) -> str:
    e = (engine or "auto").lower()
    if e in ("vtracer", "potrace"):
        return e
    # auto: prefer Potrace for very low color counts — but only if potrace + IM exist
    if max_colors <= 2 and _have("potrace") and _imagemagick_bin():
        return "potrace"
    return "vtracer"

# -------------------------------------------------
# API: /vectorize
# -------------------------------------------------
@app.post("/vectorize", response_class=PlainTextResponse)
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(4),
    smoothing: str = Form("precision"),   # "precision" | "smooth"
    primitive_snap: bool = Form(False),
    min_path_area: str = Form(None),
    corner_threshold: str = Form("30"),
    filter_speckle: str = Form("4"),
    engine: str = Form("auto"),           # "auto" | "vtracer" | "potrace"
    threshold: str = Form(None),          # Potrace threshold (0..100), else auto (Otsu)
):
    ext = ".png" if (file.content_type or "").lower().endswith("png") else ".jpg"
    in_path = _save_upload(file, suffix=ext)
    out_path = tempfile.mktemp(suffix=".svg")

    selected = choose_engine(engine, int(max_colors), smoothing)
    mode = "spline" if smoothing in ("smooth", "spline") else "polygon"

    try:
        if selected == "vtracer":
            cmd = vtracer_cmd(
                in_path, out_path,
                mode=mode,
                max_colors=int(max_colors),
                corner_threshold=float(corner_threshold or 30),
                filter_speckle=int(filter_speckle or 4),
            )
            proc = _run(cmd)
        else:
            thr = int(threshold) if (threshold and str(threshold).isdigit()) else None
            proc = potrace_pipeline(in_path, out_path, thr)
            cmd = ["potrace", "(pipeline)"]

        if proc.returncode != 0:
            return JSONResponse(status_code=500, content={
                "error": "vectorization failed",
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "cmd": cmd
            })

        if not _exists_nonempty(out_path):
            return JSONResponse(status_code=500, content={"error": "empty svg", "cmd": cmd})

        with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
            svg = f.read()
        return PlainTextResponse(svg, media_type="image/svg+xml")
    finally:
        _clean([in_path, out_path])
