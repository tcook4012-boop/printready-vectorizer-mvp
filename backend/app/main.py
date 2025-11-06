from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from PIL import Image
import io
import numpy as np
from sklearn.cluster import KMeans

app = FastAPI()

# --- CORS (allow Vercel frontend) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten to specific domains later
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Basic root & health to avoid 404 in logs ---
@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return PlainTextResponse("ok")

# --- Helpers ---
def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)

def linear_to_srgb(x):
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * (x ** (1 / 2.4)) - 0.055)

def quantize_kmeans(img_rgb, k):
    arr = img_rgb.astype(np.float32) / 255.0
    lin = srgb_to_linear(arr)
    H, W, _ = lin.shape
    flat = lin.reshape(-1, 3)

    km = KMeans(n_clusters=k, n_init=4, max_iter=50, random_state=0)
    labels = km.fit_predict(flat)
    centers_lin = km.cluster_centers_
    centers = (linear_to_srgb(centers_lin) * 255.0).clip(0, 255).astype(np.uint8)

    return labels.reshape(H, W), centers  # labels_img, palette

def palette_luminance_srgb(palette):
    rgb = palette.astype(np.float32) / 255.0
    lin = srgb_to_linear(rgb)
    R, G, B = lin[:, 0], lin[:, 1], lin[:, 2]
    return 0.2126 * R + 0.7152 * G + 0.0722 * B

def raster_to_svg_contours(labels_img, palette, min_area_px, order="light_to_dark", eps_factor=0.0015):
    import cv2  # opencv-python-headless

    H, W = labels_img.shape
    lum = palette_luminance_srgb(palette)
    idx = np.argsort(lum)  # light -> dark
    if order == "dark_to_light":
        idx = idx[::-1]

    paths = []
    diag = (H**2 + W**2) ** 0.5
    eps = eps_factor * diag

    for lab in idx:
        mask = (labels_img == lab).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for c in cnts:
            area = cv2.contourArea(c)
            if area < min_area_px:
                continue
            approx = cv2.approxPolyDP(c, eps, True)
            d = "M " + " ".join(f"{p[0][0]},{p[0][1]}" for p in approx) + " Z"
            r, g, b = palette[lab]
            fill = f"#{r:02x}{g:02x}{b:02x}"
            paths.append(f'<path d="{d}" fill="{fill}" />')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'preserveAspectRatio="xMidYMid meet">{"".join(paths)}</svg>'
    )
    return svg

# --- Vectorize API ---
@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(4),
    primitive_snap: bool = Form(False),
    smoothness: str = Form("medium"),          # "low"|"medium"|"high"
    min_path_area: float = Form(0.0005),       # fraction of W*H
    order: str = Form("light_to_dark")         # or "dark_to_light"
):
    data = await file.read()
    img = Image.open(io.BytesIO(data)).convert("RGB")
    W, H = img.size
    rgb = np.array(img)

    k = int(np.clip(max_colors, 2, 8))
    labels_img, palette = quantize_kmeans(rgb, k)

    if smoothness == "low":
        eps_factor = 0.0005
    elif smoothness == "high":
        eps_factor = 0.0025
    else:
        eps_factor = 0.0015

    area_px = max(1, int(min_path_area * (W * H)))

    svg = raster_to_svg_contours(
        labels_img, palette,
        min_area_px=area_px,
        order=order,
        eps_factor=eps_factor
    )

    return JSONResponse({"svg": svg})
