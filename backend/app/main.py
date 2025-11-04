from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import tempfile, os
from app.vectorizer.pipeline import vectorize_image

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/vectorize")
async def vectorize(file: UploadFile = File(...)):
    # Save upload to a temp file
    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(file.filename)[1] or ".png")
    os.close(fd)
    try:
        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        svg_path = vectorize_image(tmp_path)

        # return the SVG text (or store and return a URL, your call)
        with open(svg_path, "r", encoding="utf-8") as f:
            svg_text = f.read()

        return JSONResponse({"svg": svg_text})
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
