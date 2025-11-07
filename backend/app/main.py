import os
import uuid
import subprocess
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from tempfile import TemporaryDirectory

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "message": "vtracer API live"}

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    colors: int = Form(6),
    mode: str = Form("color"),
    smoothing: str = Form("precision"),  # "precision" gives crisp edges
    thin_lines: bool = Form(True),        # preserve small details
    corner_threshold: float = Form(0.05)  # lower = more corner accuracy
):
    try:
        with TemporaryDirectory() as tmpdir:
            input_path = f"{tmpdir}/input.png"
            output_path = f"{tmpdir}/output.svg"

            # Save upload
            with open(input_path, "wb") as f:
                f.write(await file.read())

            # vtracer command with HIGH ACCURACY settings
            command = [
                "vtracer",
                "--input", input_path,
                "--output", output_path,
                "--mode", mode,              # color or monochrome
                "--colors", str(colors),     # palette
                "--smoothing", smoothing,    # precision = crisp edges
                "--corner-threshold", str(corner_threshold),
                "--filter-speckle", "4",     # remove tiny blobs
                "--thin-lines", "true" if thin_lines else "false"
            ]

            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode != 0 or not os.path.exists(output_path):
                raise HTTPException(500, {
                    "error": "vectorization failed",
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                    "cmd": command
                })

            # Return SVG
            with open(output_path, "r") as f:
                svg = f.read()

            return {"svg": svg}

    except Exception as e:
        raise HTTPException(500, {"error": str(e)})
