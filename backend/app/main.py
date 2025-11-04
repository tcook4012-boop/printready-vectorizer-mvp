from fastapi import FastAPI, UploadFile, File, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from app.vectorizer.pipeline import vectorize_image

app = FastAPI()

# ✅ Allow frontend access
origins = [
    "https://printready-vectorizer-mvp.vercel.app",
    "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

@app.head("/health")
def health_head():
    return Response(status_code=200)

@app.post("/api/vectorize")
async def vectorize(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        svg_output = vectorize_image(contents)
        return {"svg": svg_output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
