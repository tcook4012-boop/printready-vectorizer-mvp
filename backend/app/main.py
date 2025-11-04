# app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from typing import Optional
import tempfile
import shutil
import subprocess
from pathlib import Path

# If you already have a pipeline module that returns an SVG string, you can keep this import.
# If not present, you can comment this out and the fallback (potrace) will be used.
try:
    from app.vectorizer.pipeline import vectorize_image as pipeline_vectorize
except Exception:
    pipeline_vectorize = None  # fallback to potrace

app = FastAPI(title="PrintReady Vectorizer API", version="1.0.0")

# CORS: allow your Vercel site to call this API from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # you can restrict to ["https://printready-vectorizer-mvp.vercel.app"]
    allow_credentials=False,      # must be False when allow_origins == ["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"

def _potrace_vectorize(input_path: Path) -> str:
    """
    Minimal potrace pipeline:
    - ensure PNG input
    - run: potrace <in.png> -s -o <out.svg>
    - return SVG text
    NOTE: requires potrace installed in the container (which your Dockerfile now does).
    """
    if input_path.suffix.lower() != ".png":
        # convert to png via imagemagick 'convert' if available; otherwise assume it's already PNG
        # We keep it simple to avoid adding runtime Python deps (Pillow) unless you want them.
        tmp_png = input_path.with_suffix(".png")
        try:
            subprocess.run(
                ["convert", str(input_path), str(tmp_png)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            input_path = tmp_png
        except Exception:
            # If convert is not available, just proceed with what we have; many rasters are already png/jpg
            pass

    out_svg = input_path.with_suffix(".svg")
    proc = subprocess.run(
        ["potrace", str(input_path), "-s", "-o", str(out_svg)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"potrace failed: {proc.stderr.strip() or proc.stdout.strip()}")

    return out_svg.read_text(encoding="utf-8")

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: Optional[int] = Form(None),
    smoothness: Optional[str] = Form(None),
    primitive_snap: Optional[bool] = Form(None),
):
    """
    Accepts multipart/form-data with 'file'.
    Optional form fields are accepted (ignored by the simple potrace fallback).
    Returns: { "svg": "<svg ...>" }
    """
    try:
        # Persist upload to a temp file
        suffix = ""
        if file.filename and "." in file.filename:
            suffix = "." + file.filename.rsplit(".", 1)[-1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)
            await file.seek(0)
            shutil.copyfileobj(file.file, tmp)

        # Prefer your existing pipeline if available
        if pipeline_vectorize is not None:
            # Many users implement vectorize_image to accept a path and return SVG text.
            # If your signature is different, adapt here.
            svg_text = pipeline_vectorize(str(tmp_path))
        else:
            svg_text = _potrace_vectorize(tmp_path)

        return {"svg": svg_text}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            if "tmp_path" in locals() and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
                # also delete sibling .svg/.png if created
                for sib in (tmp_path.with_suffix(".svg"), tmp_path.with_suffix(".png")):
                    if sib.exists():
                        sib.unlink(missing_ok=True)
        except Exception:
            pass
