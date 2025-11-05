from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.vectorizer.pipeline import vectorize_image

app = FastAPI(title="PrintReady Vectorizer API")

# CORS: adjust the allow_origins to your Vercel app domain(s)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://printready-vectorizer-mvp.vercel.app",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(8),
    smoothness: str = Form("medium"),
    primitive_snap: bool = Form(True),
):
    """
    Accepts an uploaded raster, converts to BMP (potrace-friendly), runs potrace,
    and returns the SVG TEXT (not a temp file path).
    """
    data = await file.read()
    try:
        svg_text = vectorize_image(
            input_bytes=data,
            max_colors=max_colors,
            smoothness=smoothness,
            primitive_snap=primitive_snap,
        )
        # Return SVG string directly so the frontend can display it
        return JSONResponse({"svg": svg_text})
    except Exception as e:
        # Surface a helpful error message to Swagger and the frontend
        return JSONResponse({"detail": str(e)}, status_code=500)
