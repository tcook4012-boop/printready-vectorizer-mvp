# app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from typing import Optional
import tempfile
import shutil
import subprocess
from pathlib import Path

try:
    from app.vectorizer.pipeline import vectorize_image as pipeline_vectorize
except Exception:
    pipeline_vectorize = None

app = FastAPI(title="PrintReady Vectorizer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"

def _potrace_vectorize(input_path: Path) -> str:
    # Convert to PNG if needed
    if input_path.suffix.lower() != ".png":
        png_path = input_path.with_suffix(".png")
        try:
            subprocess.run(
                ["convert", str(input_path), str(png_path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            input_path = png_path
        except Exception:
            pass

    out_svg = input_path.with_suffix(".svg")
    proc = subprocess.run(
        ["potrace", str(input_path), "-s", "-o", str(out_svg)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"potrace failed: {proc.stderr.strip()}")

    # ✅ FIX — read and return SVG text, not the file path
    return out_svg.read_text(encoding="utf-8")

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: Optional[int] = Form(None),
    smoothness: Optional[str] = Form(None),
    primitive_snap: Optional[bool] = Form(None),
):
    try:
        suffix = ""
        if file.filename and "." in file.filename:
            suffix = "." + file.filename.rsplit(".", 1)[-1].lower()

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)
            await file.seek(0)
            shutil.copyfileobj(file.file, tmp)

        if pipeline_vectorize:
            svg_text = pipeline_vectorize(str(tmp_path))
        else:
            svg_text = _potrace_vectorize(tmp_path)

        return {"svg": svg_text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp files
        try:
            if "tmp_path" in locals() and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
                for sib in (tmp_path.with_suffix(".svg"), tmp_path.with_suffix(".png")):
                    if sib.exists():
                        sib.unlink(missing_ok=True)
        except:
            pass
