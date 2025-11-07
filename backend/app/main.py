# backend/app/main.py
import os
import shutil
import subprocess
import tempfile
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import PlainTextResponse, JSONResponse

app = FastAPI()

def build_cmd(
    inp: str,
    outp: str,
    *,
    mode: str = "polygon",            # "polygon" | "spline" | "color" (color mode ignored here)
    max_colors: int = 4,
    corner_threshold: float = 30.0,
    filter_speckle: int = 4,
):
    # vtracer 0.6.5 flags that actually exist:
    # --mode, --color_precision, --corner_threshold, --filter_speckle, --input, --output
    return [
        "vtracer",
        "--input", inp,
        "--output", outp,
        "--mode", mode,
        "--color_precision", str(max_colors),
        "--corner_threshold", str(int(corner_threshold)),  # must be integer-like for this build
        "--filter_speckle", str(int(filter_speckle)),
    ]

def save_upload_to_temp(upload: UploadFile, suffix: str = ".jpg") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as tmp:
        shutil.copyfileobj(upload.file, tmp)
        tmp.flush()
        os.fsync(tmp.fileno())
    return path

@app.post("/vectorize", response_class=PlainTextResponse)
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(4),
    smoothing: str = Form("precision"),
    primitive_snap: bool = Form(False),
    min_path_area: str = Form(None),
    corner_threshold: str = Form("30"),
    filter_speckle: str = Form("4"),
):
    # pick extension from content-type (fallback .jpg)
    ext = ".png" if (file.content_type or "").lower().endswith("png") else ".jpg"
    in_path = save_upload_to_temp(file, suffix=ext)
    out_path = tempfile.mktemp(suffix=".svg")

    # map UI smoothing to vtracer mode
    mode = "spline" if smoothing in ("smooth", "spline") else "polygon"

    try:
        cmd = build_cmd(
            in_path,
            out_path,
            mode=mode,
            max_colors=int(max_colors),
            corner_threshold=float(corner_threshold or 30),
            filter_speckle=int(filter_speckle or 4),
        )
        proc = subprocess.run(cmd, capture_output=True, text=True)

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

        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            return JSONResponse(
                status_code=500,
                content={"error": "empty svg", "cmd": cmd},
            )

        with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
            svg = f.read()

        # Return raw SVG text (frontend now supports raw SVG or JSON)
        return PlainTextResponse(svg, media_type="image/svg+xml")

    finally:
        # cleanup
        try:
            if os.path.exists(in_path): os.remove(in_path)
        except: pass
        try:
            if os.path.exists(out_path): os.remove(out_path)
        except: pass
