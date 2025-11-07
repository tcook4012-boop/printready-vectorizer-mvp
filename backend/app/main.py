import os
import shutil
import subprocess
import tempfile
import zipfile
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import PlainTextResponse, JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

app = FastAPI(title="PrintReady Vectorizer API")

# -----------------------------
# Utilities
# -----------------------------
def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)

def _exists_and_nonempty(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0

def save_upload_to_temp(upload: UploadFile, suffix: str = ".jpg") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as tmp:
        shutil.copyfileobj(upload.file, tmp)
        tmp.flush()
        os.fsync(tmp.fileno())
    return path

def _clean_temp(paths: List[str]):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except:
            pass

# -----------------------------
# VTracer (multi-color) driver
# -----------------------------
def vtracer_cmd(inp: str, outp: str, *, mode: str = "polygon",
                max_colors: int = 4, corner_threshold: float = 30.0,
                filter_speckle: int = 4) -> List[str]:
    return [
        "vtracer",
        "--input", inp,
        "--output", outp,
        "--mode", mode,  # "polygon" or "spline"
        "--color_precision", str(max_colors),
        "--corner_threshold", str(int(corner_threshold)),
        "--filter_speckle", str(int(filter_speckle)),
    ]

# -----------------------------
# Potrace (mono/duo-color) driver
# Notes:
# - Potrace is fundamentally monochrome. For 2-color logos, we threshold twice
#   from adaptive levels and merge; here we start with single-threshold for stability.
# -----------------------------
def potrace_svg(inp: str, outp: str, *, threshold: Optional[int] = None) -> subprocess.CompletedProcess:
    # If a threshold is provided, use ImageMagick to binarize first
    work_inp = inp
    temp_binarized = None
    try:
        if threshold is not None:
            temp_binarized = tempfile.mktemp(suffix=".png")
            # Convert to grayscale + threshold
            # Using ImageMagick: -colorspace Gray -threshold X%
            cmd_magick = ["convert", inp, "-colorspace", "Gray", "-threshold", f"{threshold}%", temp_binarized]
            proc_m = _run(cmd_magick)
            if proc_m.returncode != 0 or not _exists_and_nonempty(temp_binarized):
                return proc_m
            work_inp = temp_binarized

        # Use mkbitmap (if available) for smoothing before potrace
        temp_pgm = tempfile.mktemp(suffix=".pgm")
        proc_bm = _run(["mkbitmap", "-f", "4", "-s", "2", "-o", temp_pgm, work_inp])
        if proc_bm.returncode != 0 or not _exists_and_nonempty(temp_pgm):
            # Fallback: let potrace read source directly
            proc = _run(["potrace", "-s", "-o", outp, work_inp])
        else:
            proc = _run(["potrace", "-s", "-o", outp, temp_pgm])

        # Clean temp pgm
        try:
            if os.path.exists(temp_pgm):
                os.remove(temp_pgm)
        except:
            pass

        return proc
    finally:
        if temp_binarized:
            try:
                os.remove(temp_binarized)
            except:
                pass

# -----------------------------
# Engine selection
# -----------------------------
def choose_engine(engine: str, max_colors: int, smoothing: str) -> str:
    e = (engine or "auto").lower()
    if e in ("vtracer", "potrace"):
        return e
    # Auto: prefer Potrace for mono/duo-color logos and precise edges
    if max_colors <= 2 or smoothing == "precision":
        return "potrace"
    return "vtracer"

# -----------------------------
# API: Single vectorize
# -----------------------------
@app.post("/vectorize", response_class=PlainTextResponse)
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(4),
    smoothing: str = Form("precision"),  # "precision" or "smooth"
    primitive_snap: bool = Form(False),  # (reserved)
    min_path_area: str = Form(None),     # (reserved)
    corner_threshold: str = Form("30"),
    filter_speckle: str = Form("4"),
    engine: str = Form("auto"),          # "auto" | "vtracer" | "potrace"
    threshold: str = Form(None),         # Potrace binarization threshold percent (e.g., "60")
):
    ext = ".png" if (file.content_type or "").lower().endswith("png") else ".jpg"
    in_path = save_upload_to_temp(file, suffix=ext)
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
            thr = int(threshold) if threshold is not None and str(threshold).isdigit() else None
            cmd = ["potrace", "(see code: via mkbitmap/convert pipeline)"]
            proc = potrace_svg(in_path, out_path, threshold=thr)

        if proc.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={"error": "vectorization failed", "stdout": proc.stdout, "stderr": proc.stderr, "cmd": cmd},
            )

        if not _exists_and_nonempty(out_path):
            return JSONResponse(status_code=500, content={"error": "empty svg", "cmd": cmd})

        with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
            svg = f.read()

        return PlainTextResponse(svg, media_type="image/svg+xml")
    finally:
        _clean_temp([in_path, out_path])

# -----------------------------
# API: Batch vectorize → ZIP
# -----------------------------
@app.post("/batch")
async def batch_vectorize(
    files: List[UploadFile] = File(...),
    max_colors: int = Form(4),
    smoothing: str = Form("precision"),
    corner_threshold: str = Form("30"),
    filter_speckle: str = Form("4"),
    engine: str = Form("auto"),
    threshold: str = Form(None),
):
    tmp_dir = tempfile.mkdtemp(prefix="vec_batch_")
    zip_path = os.path.join(tmp_dir, "result.zip")
    cleanup_paths = [tmp_dir, zip_path]

    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for idx, upload in enumerate(files):
                name_base = os.path.splitext(upload.filename or f"file_{idx}")[0]
                ext = ".png" if (upload.content_type or "").lower().endswith("png") else ".jpg"
                in_path = save_upload_to_temp(upload, suffix=ext)
                out_path = os.path.join(tmp_dir, f"{name_base}.svg")

                selected = choose_engine(engine, int(max_colors), smoothing)
                mode = "spline" if smoothing in ("smooth", "spline") else "polygon"

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
                    thr = int(threshold) if threshold is not None and str(threshold).isdigit() else None
                    proc = potrace_svg(in_path, out_path, threshold=thr)

                if proc.returncode != 0 or not _exists_and_nonempty(out_path):
                    # Write an error marker file instead of failing the whole batch
                    err_txt = os.path.join(tmp_dir, f"{name_base}__ERROR.txt")
                    with open(err_txt, "w", encoding="utf-8") as ef:
                        ef.write(f"Vectorization failed for {upload.filename}\n\nstdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}\n")
                    zf.write(err_txt, arcname=os.path.basename(err_txt))
                else:
                    zf.write(out_path, arcname=os.path.basename(out_path))

                _clean_temp([in_path])  # keep svg until zipped

        def _cleanup():
            _clean_temp(cleanup_paths)

        return StreamingResponse(
            open(zip_path, "rb"),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=vectorized.zip"},
            background=BackgroundTask(_cleanup),
        )
    except Exception as e:
        _clean_temp(cleanup_paths)
        return JSONResponse(status_code=500, content={"error": f"batch failed: {e}"})
