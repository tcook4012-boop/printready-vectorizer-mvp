from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from app.vectorizer.pipeline import vectorize_image
import io

app = FastAPI(title="PrintReady Vectorizer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(8),
    smoothness: str = Form("medium"),
    primitive_snap: bool = Form(True),
    hq_refine: bool = Form(False),
    min_feature_px: int = Form(4),
):
    content = await file.read()
    svg_bytes, metrics = vectorize_image(
        content,
        max_colors=max_colors,
        smoothness=smoothness,
        primitive_snap=primitive_snap,
        hq_refine=hq_refine,
        min_feature_px=min_feature_px,
    )
    headers = {"X-Metrics": metrics.to_json()}
    return Response(content=svg_bytes, media_type="image/svg+xml", headers=headers)

@app.get("/health")
def health():
    return JSONResponse({"ok": True})
