from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from tempfile import NamedTemporaryFile
import subprocess
import shutil
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def build_vtracer_cmd(
    in_path: str,
    out_path: str,
    *,
    mode: str,
    color_precision: int,
    corner_threshold: int,
    filter_speckle: int
) -> list[str]:
    return [
        "vtracer",
        "--input", in_path,
        "--output", out_path,
        "--mode", mode,
        "--color_precision", str(color_precision),
        "--corner_threshold", str(corner_threshold),
        "--filter_speckle", str(filter_speckle),
    ]

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    maxColors: int = Form(4),
    smoothing: str = Form("smooth"),
    cornerThreshold: str = Form("30"),
    filterSpeckle: int = Form(4),
):
    # save input
    with NamedTemporaryFile(delete=False, suffix=".png") as tmp_in:
        shutil.copyfileobj(file.file, tmp_in)
        in_path = tmp_in.name

    out_path = in_path.replace(".png", ".svg")

    # force valid integers only — vtracer rejects decimals
    try:
        color_precision = int(maxColors)
    except:
        color_precision = 4

    try:
        corner_threshold = int(float(cornerThreshold))
    except:
        corner_threshold = 30

    try:
        filter_speckle = int(filterSpeckle)
    except:
        filter_speckle = 4

    mode = "spline" if smoothing == "smooth" else "polygon"

    cmd = build_vtracer_cmd(
        in_path,
        out_path,
        mode=mode,
        color_precision=color_precision,
        corner_threshold=corner_threshold,
        filter_speckle=filter_speckle,
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60
    )

    # failure
    if not os.path.exists(out_path):
        return {
            "error": "vectorization failed",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "cmd": cmd,
            "snippet": result.stdout[:200] if result.stdout else "",
        }

    svg = open(out_path, "r", encoding="utf-8").read()

    os.remove(in_path)
    os.remove(out_path)

    return {"svg": svg}

@app.get("/health")
async def health():
    return {"status": "ok"}
