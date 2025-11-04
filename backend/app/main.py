from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from app.vectorizer.pipeline import vectorize_image

app = FastAPI(title="PrintReady Vectorizer API")

# allow your Vercel app to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later to your vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(8),
    smoothness: str = Form("medium"),
    primitive_snap: bool = Form(True),
):
    """
    Returns: {"svg": "<svg ...>"}  (inline SVG text, not a tmp path)
    """
    data = await file.read()
    svg_text = vectorize_image(
        data=data,
        max_colors=max_colors,
        smoothness=smoothness,
        primitive_snap=primitive_snap,
    )
    return JSONResponse({"svg": svg_text})


# Optional: simple passthrough to view an SVG string directly (handy for debugging)
@app.post("/vectorize.svg")
async def vectorize_svg(
    file: UploadFile = File(...),
    max_colors: int = Form(8),
    smoothness: str = Form("medium"),
    primitive_snap: bool = Form(True),
):
    data = await file.read()
    svg_text = vectorize_image(
        data=data,
        max_colors=max_colors,
        smoothness=smoothness,
        primitive_snap=primitive_snap,
    )
    return PlainTextResponse(svg_text, media_type="image/svg+xml")
