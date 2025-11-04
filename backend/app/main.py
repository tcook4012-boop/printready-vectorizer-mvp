from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from app.vectorizer.pipeline import vectorize_image

app = FastAPI()

@app.head("/health")
@app.get("/health")
def health():
    return JSONResponse({"ok": True})

@app.get("/")
def root():
    return JSONResponse({"service": "printready-vectorizer-api", "status": "up"})

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(8),
    smoothness: str = Form("medium"),
    primitive_snap: bool = Form(True),
    min_feature_px: int = Form(4),
):
    img_bytes = await file.read()

    svg_bytes, metrics = vectorize_image(
        img_bytes=img_bytes,
        max_colors=max_colors,
        smoothness=smoothness,
        primitive_snap=primitive_snap,
        min_feature_px=min_feature_px,
    )

    return Response(content=svg_bytes, media_type="image/svg+xml")
