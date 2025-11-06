from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from PIL import Image
import io
import numpy as np
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

def srgb_to_linear(x: np.ndarray) -> np.ndarray:
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x: np.ndarray) -> np.ndarray:
    # Guard against tiny negatives/NaNs from numerical error
    x = np.nan_to_num(x, nan=0.0)
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * (x ** (1.0 / 2.4)) - 0.055)


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

    # 1) grayscale
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # 2) Otsu (invert) => dark ink = 255 foreground, background = 0
    _thr, mask = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    # 3) light despeckle
    kernel = np.ones((2, 2), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # 4) contours on foreground
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    # 5) build paths; skip near-full-frame to avoid black rectangle
    full_frame_cutoff = 0.98 * (W * H)
    paths = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < min_area_px or area >= full_frame_cutoff:
            continue

        approx = cv2.approxPolyDP(c, eps_px, True)
        if len(approx) < 3:
            continue

        d = "M " + " ".join(f"{p[0][0]},{p[0][1]}" for p in approx) + " Z"
        paths.append(f'<path d="{d}" fill="#000000"/>')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'preserveAspectRatio="xMidYMid meet">{"".join(paths)}</svg>'
    )
    return svg, len(paths)


# =================================================================
# --------------------- K-Means Color Pipeline --------------------
# =================================================================

def quantize_kmeans(rgb: np.ndarray, k: int):
    arr = rgb.astype(np.float32) / 255.0
    lin = srgb_to_linear(arr)
    H, W, _ = lin.shape
    flat = lin.reshape(-1, 3)

    km = KMeans(n_clusters=int(k), n_init=4, max_iter=50, random_state=0)
    labels = km.fit_predict(flat)
    centers_lin = km.cluster_centers_

    centers = (linear_to_srgb(centers_lin) * 255.0).clip(0, 255).astype(np.uint8)
    return labels.reshape(H, W), centers


def palette_luminance_srgb(palette: np.ndarray) -> np.ndarray:
    rgb = palette.astype(np.float32) / 255.0
    lin = srgb_to_linear(rgb)
    R, G, B = lin[:, 0], lin[:, 1], lin[:, 2]
    return 0.2126 * R + 0.7152 * G + 0.0722 * B


def raster_to_svg_contours(labels_img: np.ndarray, palette: np.ndarray,
                           min_area_px: int, order: str, eps_px: float):
    import cv2

    H, W = labels_img.shape

    lum = palette_luminance_srgb(palette)
    idx = np.argsort(lum)  # light→dark
    if order == "dark_to_light":
        idx = idx[::-1]

    paths = []
    for lab in idx:
        mask = (labels_img == lab).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        for c in cnts:
            area = cv2.contourArea(c)
            if area < min_area_px:
                continue

            approx = cv2.approxPolyDP(c, eps_px, True)
            if len(approx) < 3:
                continue

            d = "M " + " ".join(f"{p[0][0]},{p[0][1]}" for p in approx) + " Z"
            r, g, b = palette[lab]
            paths.append(f'<path d="{d}" fill="#{r:02x}{g:02x}{b:02x}"/>')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'preserveAspectRatio="xMidYMid meet">{"".join(paths)}</svg>'
    )
    return svg, len(paths)


# =================================================================
# -------------------------- Main Endpoint ------------------------
# =================================================================

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(4),
    primitive_snap: bool = Form(False),
    smoothness: str = Form("medium"),
    min_path_area: float = Form(0.0005),
    order: str = Form("dark_to_light")
):
    data = await file.read()
    rgb, (W, H) = image_to_np_rgb(data)

    diag = (W ** 2 + H ** 2) ** 0.5

    # simplification tolerance (px)
    eps_factor = 0.0015
    if smoothness == "low":
        eps_factor = 0.0005
    elif smoothness == "high":
        eps_factor = 0.0025
    eps_px = float(np.clip(eps_factor * diag, 0.5, 0.05 * diag))

    # area threshold
    area_px = max(1, int(float(min_path_area) * (W * H)))

    # auto B/W detection: two colors OR very low saturation
    sat = mean_saturation(rgb)
    use_bw = (int(max_colors) <= 2) or (sat < 0.10)

    if use_bw:
        svg, npaths = vectorize_bw_otsu(rgb, area_px, eps_px)
        return JSONResponse({"svg": svg}, headers={"X-Mode": "bw-otsu", "X-Paths": str(npaths)})

    # multicolor path
    k = int(np.clip(max_colors, 2, 8))
    labels_img, palette = quantize_kmeans(rgb, k)
    svg, npaths = raster_to_svg_contours(labels_img, palette, area_px, order, eps_px)
    return JSONResponse({"svg": svg}, headers={"X-Mode": "kmeans", "X-Paths": str(npaths)})
