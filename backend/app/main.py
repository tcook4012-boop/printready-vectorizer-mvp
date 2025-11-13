# backend/app/main.py

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# We now route all vectorization through the dualmode wrapper.
from app.pipeline.logo_dualmode import vectorize_logo_dualmode_to_svg_bytes

app = FastAPI(title="PrintReady Vectorizer API")

# Allow frontend origin (Vercel) to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later if you want
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/vectorize")
async def vectorize(file: UploadFile = File(...)):
    """
    Main vectorization endpoint.

    - Accepts: multipart/form-data with 'file'
    - Returns: JSON { "svg": "<svg ...>...</svg>" }

    NOTE:
    -----
    We intentionally do NOT enforce a '<svg' sanity check here, because the
    frontend already validates that the response is usable SVG and shows a
    helpful error message if not. This keeps backend behaviour closer to the
    original version you had before the dual-mode refactor.
    """
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Empty file upload")

        svg_bytes = vectorize_logo_dualmode_to_svg_bytes(image_bytes)
        svg_text = svg_bytes.decode("utf-8", errors="replace")

        # Always return whatever the pipeline produced; frontend will decide
        # whether it is valid/usable SVG.
        return JSONResponse({"svg": svg_text})
    except HTTPException:
        # Preserve explicit HTTPException status codes
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        raise HTTPException(status_code=500, detail=f"vectorization failed: {e}")


# Local dev (from backend/app):
#   uvicorn main:app --reload --host 0.0.0.0 --port 8000
