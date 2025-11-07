# backend/app/main.py
import os
import re
import io
import shutil
import tempfile
import subprocess
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from PIL import Image

app = FastAPI(title="PrintReady Vectorizer API", version="0.2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- helpers ----------------

def _clean_svg(svg: str) -> str:
    svg = svg.lstrip("\ufeff")
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg, flags=re.I)
    svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg, flags=re.I)
    return svg.strip()

def _looks_like_svg_root(s: str) -> bool:
    return bool(re.match(r"^\s*<\s*svg[\s>]", s, flags=re.I))

def _safe_bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"1", "true", "yes", "on"}

def _to_float(val: Optional[str], default: float) -> float:
    try:
        return float(val) if (val is not None and str(val).strip() != "") else default
    except Exception:
        return default

def _to_int(val: Optional[str], default: int) -> int:
    try:
        return int(val) if (val is not None and str(val).strip() != "") else default
    except Exception:
        return default

def _clamp(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))

def build_cmd_long(
    vtracer_bin: str,
    in_path: str,
    out_path: str,
    *,
    mode: str,
    color_precision: int,
    corner_threshold: float,
    filter_speckle: int,
    segment_length: float,
    splice_threshold: float,
    hierarchical: str,
    thin_lines: bool,
):
    return [
        vtracer_bin,
        "--input", in_path,
        "--output", out_path,
        "--mode", mode,                           # spline | polygon
        "--color_precision", str(color_precision),
        "--corner_threshold", str(corner_threshold),
        "--filter_speckle", str(filter_speckle),
        "--segment_length", str(segment_length),
        "--splice_threshold", str(splice_threshold),
        "--hierarchical", hierarchical,           # stacked | none
        "--thin_lines", "true" if thin_lines else "false",
    ]

def build_cmd_minimal(vtracer_bin: str, in_path: str, out_path: str, *, mode: str, color_precision: int):
    # Minimal, conservative flags known to work on 0.6.5
    return [
        vtracer_bin,
        "--input", in_path,
        "--output", out_path,
        "--mode", mode,                           # spline | polygon
        "--color_precision", str(color_precision)
    ]

def _ensure_png_to_path(upload_bytes: bytes, out_png_path: str) -> None:
    # Normalize to RGB/RGBA PNG so vtracer gets something clean
    with Image.open(io.BytesIO(upload_bytes)) as im:
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
        im.save(out_png_path, format="PNG", optimize=True)

# ---------------- routes ----------------

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    maxColors: Optional[int] = Form(None),
    smoothing: Optional[str] = Form(None),       # "smooth" | "sharp"
    primitiveSnap: Optional[str] = Form(None),   # ignored at CLI; you can pre-clean upstream
    cornerThreshold: Optional[str] = Form(None),
    filterSpeckle: Optional[str] = Form(None),
    thinLines: Optional[str] = Form(None),
):
    vtracer_bin = os.environ.get("VTRACER_PATH", "vtracer")
    vtracer_path = shutil.which(vtracer_bin)
    if not vtracer_path:
        return JSONResponse(status_code=500, content={"error": f"'{vtracer_bin}' not found on PATH"})

    # More verbose Rust errors
    env = {**os.environ, "RUST_BACKTRACE": "1"}

    tmpdir = tempfile.mkdtemp(prefix="vtrace_")
    in_png = os.path.join(tmpdir, "input.png")
    out_svg = os.path.join(tmpdir, "output.svg")

    try:
        raw = await file.read()
        if not raw:
            return JSONResponse(status_code=400, content={"error": "empty upload"})

        # Always normalize to PNG
        _ensure_png_to_path(raw, in_png)

        # Map UI → vtracer
        color_precision = _clamp(int(maxColors) if maxColors is not None else 8, 1, 64)
        mode = "spline" if (smoothing or "").strip().lower() == "smooth" else "polygon"
        corner = _to_float(cornerThreshold, 10.0)
        speckle = _to_int(filterSpeckle, 4)
        seglen = 3.0
        splice = 5.0
        hier = "stacked"
        thin = _safe_bool(thinLines, False)

        # Pass 1: full featured flags
        cmd1 = build_cmd_long(
            vtracer_path, in_png, out_svg,
            mode=mode,
            color_precision=color_precision,
            corner_threshold=corner,
            filter_speckle=speckle,
            segment_length=seglen,
            splice_threshold=splice,
            hierarchical=hier,
            thin_lines=thin,
        )
        p1 = subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)

        if p1.returncode != 0 or not os.path.exists(out_svg):
            # Pass 2: minimal fallback (keeps you moving even if some flags are unsupported)
            cmd2 = build_cmd_minimal(vtracer_path, in_png, out_svg, mode=mode, color_precision=color_precision)
            p2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)

            if p2.returncode != 0 or not os.path.exists(out_svg):
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "vectorization failed",
                        "attempts": [
                            {"cmd": cmd1, "returncode": p1.returncode, "stdout": p1.stdout, "stderr": p1.stderr},
                            {"cmd": cmd2, "returncode": p2.returncode, "stdout": p2.stdout, "stderr": p2.stderr},
                        ],
                        "notes": "See stderr above. We try a minimal fallback after the full-flag attempt.",
                    },
                )

        # Read and sanitize SVG
        with open(out_svg, "r", encoding="utf-8", errors="replace") as fh:
            svg = _clean_svg(fh.read())

        if not _looks_like_svg_root(svg):
            return JSONResponse(
                status_code=500,
                content={"error": "output is not an <svg> root", "snippet": svg[:200]},
            )

        return {"svg": svg}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"{e.__class__.__name__}: {e}"})
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
