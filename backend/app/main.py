import io
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # lock down later to your vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------- Helpers -------------------------------------------------------

def safe_int(v: Optional[str], default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default

def safe_float(v: Optional[str], default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default

def pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def write_bytes(p: Path, data: bytes):
    with open(p, "wb") as f:
        f.write(data)

def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

def has_binary(name: str) -> bool:
    return subprocess.call(["which", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

# ------------- Engines -------------------------------------------------------

def vtracer_vectorize(png_path: Path, out_svg: Path, colors: int, smoothness: str,
                      min_path_area_frac: float) -> tuple[bool, str]:
    """
    Call vtracer for multi-color/vector logos.
    Flags chosen to balance fidelity + cleanliness.
    """
    # Map UI smoothness to vtracer's corner/curve tuning
    # Low(faster, sharper) -> stronger corner preservation; High -> smoother curves
    if smoothness.lower().startswith("low"):
        corner_threshold = "0.9"
        splice_threshold = "0.9"
    elif smoothness.lower().startswith("medium"):
        corner_threshold = "0.7"
        splice_threshold = "0.7"
    else:
        corner_threshold = "0.5"
        splice_threshold = "0.5"

    # min_path_area_frac (e.g., 0.0002) -> pixels based on image area
    with Image.open(png_path) as im:
        area = im.width * im.height
    min_area_px = max(1, int(area * max(0.0, min(min_path_area_frac, 0.01))))

    cmd = [
        "vtracer",
        "--mode", "color",
        "--colors", str(max(2, min(colors, 8))),
        "--hierarchical", "true",
        "--layers", "1",
        "--corner-threshold", corner_threshold,
        "--splice-threshold", splice_threshold,
        "--filter-speckle", str(min_area_px),       # remove tiny specks
        "--path-omit", str(min_area_px),            # omit tiny paths
        "--output", str(out_svg),
        str(png_path),
    ]

    res = run_cmd(cmd)
    ok = (res.returncode == 0 and out_svg.exists() and out_svg.stat().st_size > 0)
    err = res.stderr.decode("utf-8", errors="ignore")
    return ok, err

def potrace_vectorize_bw(png_path: Path, out_svg: Path,
                         threshold: int = 200,
                         turdsize: int = 4,
                         opttolerance: float = 0.2) -> tuple[bool, str]:
    """
    High-quality black/white tracing via potrace.
    We raster-threshold to PBM, then trace to SVG.
    """
    tmp_dir = png_path.parent
    pbm_path = tmp_dir / "trace_input.pbm"

    # Convert to 1-bit PBM with a solid threshold
    with Image.open(png_path) as im:
        gray = im.convert("L")
        bw = gray.point(lambda x: 255 if x > threshold else 0, "1")
        bw.save(pbm_path, format="PPM")  # PBM/PPM works; Pillow writes as P4/P5 under the hood

    cmd = [
        "potrace",
        "-s", str(pbm_path),
        "-o", str(out_svg),
        f"--turdsize={turdsize}",              # remove tiny blobs
        f"--opttolerance={opttolerance}",      # curve simplification; lower = more detail
        "--longcoding",
    ]
    res = run_cmd(cmd)
    ok = (res.returncode == 0 and out_svg.exists() and out_svg.stat().st_size > 0)
    err = res.stderr.decode("utf-8", errors="ignore")
    return ok, err

# ------------- API -----------------------------------------------------------

@app.get("/")
def root():
    return {"ok": True, "engine": {"vtracer": has_binary("vtracer"), "potrace": has_binary("potrace")}}

@app.post("/vectorize")
async def vectorize_image(
    file: UploadFile = File(...),
    max_colors: Optional[str] = Form("4"),          # 2–8
    smoothness: Optional[str] = Form("Low (faster, sharper)"),
    primitive_snap: Optional[str] = Form("false"),  # currently unused
    min_path_area: Optional[str] = Form("0.0002"),  # fraction of pixels
    force_engine: Optional[str] = Form(None),       # "vtracer" | "potrace"
):
    try:
        content = await file.read()
        # Normalize input: ensure we feed engines a clean PNG (no color profiles surprises)
        with Image.open(io.BytesIO(content)) as im:
            im = im.convert("RGBA")  # keep alpha; bg transparent
            png_bytes = pil_to_png_bytes(im)

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            in_png = td / "in.png"
            out_svg = td / "out.svg"
            write_bytes(in_png, png_bytes)

            colors = safe_int(max_colors, 4)
            min_area_frac = safe_float(min_path_area, 0.0002)
            engine = (force_engine or "").lower()

            ok = False
            err = ""

            if engine == "potrace" or (colors <= 2 and has_binary("potrace")):
                ok, err = potrace_vectorize_bw(in_png, out_svg, threshold=200, turdsize=4, opttolerance=0.2)

                # If user asked for potrace but it failed, surface error
                if engine == "potrace":
                    if not ok:
                        return JSONResponse({"error": "potrace failed", "stderr": err}, status_code=500)
                # If fallback failed (rare), try vtracer anyway
                if not ok and has_binary("vtracer"):
                    ok, err = vtracer_vectorize(in_png, out_svg, colors=max(colors, 2),
                                                smoothness=smoothness, min_path_area_frac=min_area_frac)

            else:
                # Default to vtracer for multi-color quality
                if has_binary("vtracer"):
                    ok, err = vtracer_vectorize(in_png, out_svg, colors=colors,
                                                smoothness=smoothness, min_path_area_frac=min_area_frac)
                elif has_binary("potrace"):
                    ok, err = potrace_vectorize_bw(in_png, out_svg, threshold=200, turdsize=4, opttolerance=0.2)
                else:
                    return JSONResponse({"error": "no vectorization engine available"}, status_code=500)

            if not ok:
                return JSONResponse({"error": "vectorization failed", "stderr": err[:2000]}, status_code=500)

            svg_text = out_svg.read_text(encoding="utf-8", errors="ignore")
            # Ensure a viewBox for reliable rendering in your Next UI
            if "viewBox" not in svg_text:
                with Image.open(in_png) as im:
                    svg_text = svg_text.replace(
                        "<svg ",
                        f'<svg viewBox="0 0 {im.width} {im.height}" ',
                        1,
                    )

            return {"svg": svg_text}

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
