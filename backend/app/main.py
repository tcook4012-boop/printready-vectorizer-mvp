import os
import tempfile
import subprocess
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

# Allow browser requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# ----------- Utility: map maxColors → color precision (vtracer expects bits) ----------
def _bits_from_colors(n: int) -> int:
    if n <= 2:
        return 1
    import math
    return max(1, min(8, int(round(math.log2(max(2, n))))))

# ----------- Build vtracer command safely -----------
def build_vtracer_cmd(
    input_path: str,
    output_path: str,
    *,
    mode: str = "spline",
    max_colors: int = 16,
    corner_threshold: float = 30.0,
    filter_speckle: int = 4,
    segment_length: float = None,
    splice_threshold: float = None,
    hierarchical: str = None,
):
    cmd = [
        "vtracer",
        "--input", input_path,
        "--output", output_path,
        "--mode", mode,
        "-p", str(_bits_from_colors(max_colors)),
        "-c", str(corner_threshold),
        "-f", str(filter_speckle),
    ]

    if segment_length is not None:
        cmd += ["-l", str(segment_length)]

    if splice_threshold is not None:
        cmd += ["-s", str(splice_threshold)]

    if hierarchical in ("stacked", "cutout"):
        cmd += ["--hierarchical", hierarchical]

    return cmd

# ----------- ROUTE: /vectorize ---------------------
@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(12),
    smoothing: str = Form("spline"),     # allowed: spline, polygon, pixel
    corner_threshold: float = Form(30.0),
    filter_speckle: int = Form(4),
):
    # Save uploaded file to temp
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_in:
            tmp_in.write(await file.read())
            input_path = tmp_in.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".svg") as tmp_out:
            output_path = tmp_out.name

        # Map "smoothing" to actual vtracer modes
        mode = smoothing.lower()
        if mode not in ["spline", "polygon", "pixel"]:
            mode = "spline"

        # Build the vtracer command
        cmd = build_vtracer_cmd(
            input_path=input_path,
            output_path=output_path,
            mode=mode,
            max_colors=max_colors,
            corner_threshold=corner_threshold,
            filter_speckle=filter_speckle,
            segment_length=3.0,     # helps edges
            splice_threshold=5.0,   # reduces jagged micro-corners
            hierarchical="stacked",
        )

        # Run it
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # If vtracer errors
        if proc.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={
                    "detail": {
                        "error": "vectorization failed",
                        "stdout": proc.stdout,
                        "stderr": proc.stderr,
                        "cmd": cmd,
                    }
                },
            )

        # Return SVG text
        with open(output_path, "r", encoding="utf-8") as f:
            svg_data = f.read()

        return {"svg": svg_data}

    finally:
        # Clean up temp files
        try:
            os.remove(input_path)
        except:
            pass
        try:
            os.remove(output_path)
        except:
            pass


@app.get("/")
def root():
    return {"status": "ok", "message": "Vectorizer API is running"}
