from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from PIL import Image
import io, numpy as np
from sklearn.cluster import KMeans


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return PlainTextResponse("ok")


# =================================================================
# ----------------------- Utility Functions -----------------------
# =================================================================

def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x):
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * (x ** (1 / 2.4)) - 0.055)


def image_to_np_rgb(data: bytes):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return np.array(img), img.size  # (H,W,3), (W,H)


def mean_saturation(rgb: np.ndarray) -> float:
    arr = rgb.astype(np.float32) / 255.0
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = np.zeros_like(mx)
    mask = mx > 0
    sat[mask] = (mx[mask] - mn[mask]) / mx[mask]
    return float(sat.mean())


# =================================================================
# ------------------- Black/White Otsu Pipeline -------------------
# =================================================================

def vectorize_bw_otsu(rgb: np.ndarray, min_area_px: int, eps_px: float):
    import cv2
    H, W, _ = rgb.shape

    # grayscale
    gray = cv2.cvtColor(rgb, c
