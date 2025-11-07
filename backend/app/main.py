from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
import tempfile, subprocess, os, shutil, re

app = FastAPI()

# --- CORS: allow your Vercel origin (or temporarily "*") ---
origins = [
    "https://printready-vectorizer-mvp.vercel.app",
    "http://localhost:3000",
    # "https://*vercel.app",  # optional wildcard while testing
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Health + root (so browser tests don’t show 404) ----
@app.get("/", response_class=PlainTextResponse)
def root():
    return "ok"

@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"

# ---- your existing /vectorize POST stays the same ----
svg_root_re = re.compile(r"<svg\b[^>]*>", re.I)

@app.post("/vectorize", response_class=PlainTextResponse)
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(4),
    smoothing: str = Form("precision"),
    primitive_snap: bool = Form(False),
    min_path_area: float = Form(0.0002),
    corner_threshold: float = Form(30.0),
    filter_speckle: int = Form(4),
):
    try:
        with tempfile.TemporaryDirectory() as td:
            in_path = os.path.join(td, "input.jpg")
            out_path = os.path.join(td, "out.svg")
            with open(in_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            mode = "spline" if smoothing in ("smooth", "high") else "polygon"
            cmd = [
                "vtracer",
                "--input", in_path,
                "--output", out_path,
                "--mode", mode,
                "--color_precision", str(max_colors),
                "--corner_threshold", str(int(corner_threshold)),
                "--filter_speckle", str(int(filter_speckle)),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise HTTPException(
                    500,
                    detail={
                        "error": "vectorization failed",
                        "stdout": proc.stdout,
                        "stderr": proc.stderr,
                        "cmd": cmd,
                    },
                )

            svg_text = open(out_path, "r", encoding="utf-8", errors="ignore").read()
            if not svg_root_re.search(svg_text):
                snippet = svg_text[:180].replace("\n", " ")
                raise HTTPException(500, detail={"error": "output is not an <svg> root", "snippet": snippet})

            return PlainTextResponse(svg_text, media_type="image/svg+xml")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail={"error": str(e)})
