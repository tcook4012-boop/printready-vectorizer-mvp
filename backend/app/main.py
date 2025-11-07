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
# Helpers
# -----------------------------
def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)

def _exists_and_nonempty(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0

def _which(name: str) -> Optional[str]:
    return shutil.which(name)

def _have_potrace_stack() -> bool:
    # Potrace path relies on potrace; mkbitmap and convert are very helpful, but only potrace is strictly required.
    return _which("potrace") is not None

def _have_mkbitmap() -> bool:
    return _which("mkbitmap") is not None

def _have_convert() -> bool:
    return _which("convert") is not None

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
# VTracer driver
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
# Potrace driver (with optional mkbitmap/convert)
# -----------------------------
def potrace_svg(inp: str, outp: str, *, threshold: Optional[int] = None) -> subprocess.CompletedProcess:
    work_inp = inp
    temp_binarized = None
    temp_pgm = None
    try:
        # optional binarization via ImageMagick
        if threshold is not None and _have_convert():
            temp_binarized = tempfile.mktemp(suffix=".png")
            proc_m = _run(["convert", inp, "-colorspace", "Gray", "-threshold", f"{threshold}%", temp_binarized])
            if proc_m.returncode == 0 and _exists_and_nonempty(temp_binarized):
                work_inp = temp_binarized

        # optional smoothing via mkbitmap
        if _have_mkbitmap():
            temp_pgm = tempfile.mktemp(suffix=".pgm")
            proc_bm = _run(["mkbitmap", "-f", "4", "-s", "2", "-o", temp_pgm, work_inp])
            if proc_bm.returncode == 0 and _exists_and_nonempty(temp_pgm):
                return _run(["potrace", "-s", "-o", outp, temp_pgm])

        # fallback: potrace directly
        return _run(["potrace", "-s", "-o", outp, work_inp])
    finally:
        for p in (temp_binarized, temp_pgm):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except:
                pass

# -----------------------------
# Engine selection
# -----------------------------
def choose_engine(engine: str, max_colors: int, smoothing: str) -> str:
    e = (engine or "auto").lower()
    if e in ("vtracer", "potrace"):
        return e
    # auto:
    # prefer potrace for <=2 colors or "precision", BUT only if potrace is available
    if (max_colors <= 2 or smoothing == "precision") and _have_potrace_stack():
        return "potrace"
    return "vtracer"

# -----------------------------
# API: single vectorize
# -----------------------------
@app.post("/vectorize", response_class=PlainTextResponse)
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(4),
    smoothing: str = Form("precision"),  # "precision" | "smooth"
    primitive_snap: bool = Form(False),
    min_path_area: str = Form(None),
    corner_threshold: str = Form("30"),
    filter_speckle: str = Form("4"),
    engine: str = Form("auto"),          # "auto" | "vtracer" | "potrace"
    threshold: str = Form(None),         # Potrace threshold (%)
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
            cmd = ["potrace", "(auto)"]
            proc = potrace_svg(in_path, out_path, threshold=thr)

        if proc.returncode != 0:
            return JSONResponse(status_code=500, content={
                "error": "vectorization failed",
                "stdout": proc.stdout, "stderr": proc.stderr, "cmd": cmd
            })

        if not _exists_and_nonempty(out_path):
            return JSONResponse(status_code=500, content={"error": "empty svg", "cmd": cmd})

        with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
            svg = f.read()
        return PlainTextResponse(svg, media_type="image/svg+xml")
    finally:
        _clean_temp([in_path, out_path])

# -----------------------------
# API: batch → ZIP
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
    cleanup_paths = [zip_path, tmp_dir]

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
                    err_txt = os.path.join(tmp_dir, f"{name_base}__ERROR.txt")
                    with open(err_txt, "w", encoding="utf-8") as ef:
                        ef.write(
                            f"Vectorization failed for {upload.filename}\n\n"
                            f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}\n"
                        )
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
