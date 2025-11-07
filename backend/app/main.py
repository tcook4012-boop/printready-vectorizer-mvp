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

def build_vtracer_cmd(input_path, output_path, mode, max_colors, smoothing, primitive_snap, corner_threshold, filter_speckle, thin_lines):
    mode_flag = "polygon"
    if smoothing == "smooth":
        mode_flag = "spline"

    # ✅ Convert corner threshold to integer only
    try:
        corner_int = int(float(corner_threshold))
    except:
        corner_int = 10

    cmd = [
        "vtracer",
        "--input", input_path,
        "--output", output_path,
        "--mode", mode_flag,
        "-p", str(max_colors),          # max_colors
        "-c", str(corner_int),          # ✅ integer only
        "-f", str(filter_speckle or 4), # remove small artifacts
        "-l", "3.0",                    # segment length smoothing
        "-s", "5.0",                    # splice threshold
        "--hierarchical", "stacked"
    ]

    if thin_lines:
        cmd.append("--thin-lines")

    return cmd


@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    maxColors: int = Form(4),
    smoothing: str = Form("smooth"),
    primitiveSnap: bool = Form(False),
    cornerThreshold: str = Form("10"),
    filterSpeckle: int = Form(4),
    thinLines: bool = Form(False),
):
    # save upload
    with NamedTemporaryFile(delete=False, suffix=".png") as tmp_in:
        shutil.copyfileobj(file.file, tmp_in)
        input_path = tmp_in.name

    output_path = input_path.replace(".png", ".svg")

    cmd = build_vtracer_cmd(
        input_path,
        output_path,
        mode=None,
        max_colors=maxColors,
        smoothing=smoothing,
        primitive_snap=primitiveSnap,
        corner_threshold=cornerThreshold,
        filter_speckle=filterSpeckle,
        thin_lines=thinLines,
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
    except Exception as e:
        return {"error": "failed to execute vtracer", "exception": str(e)}

    if not os.path.exists(output_path):
        return {
            "error": "vectorization failed",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "cmd": cmd,
        }

    svg_data = open(output_path, "r", encoding="utf-8").read()

    os.remove(input_path)
    os.remove(output_path)

    return {"svg": svg_data}


@app.get("/health")
async def health():
    return {"status": "ok"}
