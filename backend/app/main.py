from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from app.vectorizer.pipeline import vectorize_image

app = FastAPI(title="PrintReady Vectorizer API", version="0.1.0")

# --- CORS ---
# Allow your Vercel frontend (add any preview domains if you have them)
origins = [
    "https://printready-vectorizer-mvp.vercel.app",
    # "https://<your-preview>.vercel.app",  # add if needed
    # You can temporarily allow "*" while testing, then tighten later:
    "*",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True, "service": "printready-vectorizer-api"}

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(8),
    smoothness: str = Form("medium"),
    primitive_snap: bool = Form(True),
):
    """
    Accepts a file upload via multipart/form-data and returns an SVG string.
    """
    image_bytes = await file.read()

    svg_text = vectorize_image(
        image_bytes=image_bytes,          # <-- correct kwarg name
        max_colors=max_colors,
        smoothness=smoothness,
        primitive_snap=primitive_snap,
    )

    return {"svg": svg_text}
