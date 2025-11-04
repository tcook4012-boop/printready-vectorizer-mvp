from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from app.vectorizer.pipeline import vectorize_image

app = FastAPI()

# Clean health checks for both HEAD and GET
@app.head("/health")
@app.get("/health")
def health():
    return JSONResponse({"ok": True})

# Optional friendly root so Render's root probe isn't a 404
@app.get("/")
def root():
    return JSONResponse({"service": "printready-vectorizer-api", "status": "up"})

# Your vectorize endpoint (unchanged behavior)
@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(8),
    smoothness: str = Form("medium"),
    primitive_snap: bool = Form(True),
    hq_refine: bool = Form(False),
    min_feature_px: int = Form(4),
):
    img_bytes = await file.read()

    svg_bytes, metrics = vectorize_image(
        img_bytes=img_bytes,
        max_colors=max_colors,
        smoothness=smoothness,
        primitive_snap=primitive_snap,
        hq_refine=hq_refine,
        min_feature_px=min_feature_px,
    )

    # Return SVG with proper content-type
    return Response(content=svg_bytes, media_type="image/svg+xml")
