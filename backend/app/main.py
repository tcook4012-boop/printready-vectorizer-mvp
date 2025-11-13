# backend/app/main.py

import io
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# NOTE:
# Previously this imported:
#   from app.pipeline.logo_safe import vectorize_logo_safe_to_svg_bytes
# We now go through a thin dual-mode wrapper so we can evolve the internals
# without touching this file again.
from app.pipeline.logo_dualmode import vectorize_logo_dualmode_to_svg_bytes

app = FastAPI(title="PrintReady Vectorizer API")

# Allow frontend origin (Vercel) to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # you can tighten this later to your exact frontend origin
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
    """
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Empty file upload")

        # Call the dual-mode wrapper. Right now this behaves exactly like the
        # existing logo_safe pipeline, but it gives us a stable hook for
        # future "logo vs sign" improvements.
        svg_bytes = vectorize_logo_dualmode_to_svg_bytes(image_bytes)
        svg_text = svg_bytes.decode("utf-8", errors="replace")

        # Minimal sanity check to catch non-SVG responses
        if "<svg" not in svg_text.lower():
            raise HTTPException(
                status_code=500,
                detail="Vectorization pipeline returned non-SVG text",
            )

        return JSONResponse({"svg": svg_text})
    except HTTPException:
        # Re-raise FastAPI HTTPExceptions so status codes are preserved
        raise
    except Exception as e:
        # Catch-all for unexpected errors, so the frontend gets a clean message
        raise HTTPException(status_code=500, detail=f"vectorization failed: {e}")


# For local dev (inside backend/app directory):
#   uvicorn main:app --reload --host 0.0.0.0 --port 8000
