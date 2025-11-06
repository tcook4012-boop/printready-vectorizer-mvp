# backend/app/main.py
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

# ---------- helpers ----------
def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)

def linear_to_srgb(x):
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * (x ** (1 / 2.4)) - 0.055)

def quantize_kmeans(img_rgb, k):
    arr = img_rgb.astype(np.float32) / 255.0
    lin = srgb_to_linear(arr)
    H, W, _ = lin.shape
    flat = lin.reshape(-1, 3)
    km = KMeans(n_clusters=int(k), n_init=4, max_iter=50, random_state=0)
    labels = km.fit_predict(flat)
    centers_lin = km.cluster_centers_
    centers = (linear_to_srgb(centers_lin) * 255.0).clip(0, 255).astype(np.uint8)
    return labels.reshape(H, W), centers  # labels_img, palette

def palette_luminance_srgb(palette):
    rgb = palette.astype(np.float32) / 255.0
    lin = srgb_to_linear(rgb)
    R, G, B = lin[:,0], lin[:,1], lin[:,2]
    return 0.2126*R + 0.7152*G + 0.0722*B

def build_svg_from_labels(labels_img, palette, min_area_px, order, eps_factor):
    import cv2
    H, W = labels_img.shape
    lum = palette_luminance_srgb(palette)
    # order index
    order_idx = np.argsort(lum)  # light->dark
    if order == "dark_to_light":
        order_idx = order_idx[::-1]

    # clamp epsilon so we never over-simplify to nothing
    diag = (H**2 + W**2) ** 0.5
    eps = float(eps_factor) * diag
    eps = max(0.5, min(eps, 0.05 * diag))  # 0.5px .. 5% of diag

    def pass_once(retr=cv2.RETR_EXTERNAL, chain=cv2.CHAIN_APPROX_NONE, min_area=int(min_area_px)):
        paths = []
        for lab in order_idx:
            mask = (labels_img == lab).astype(np.uint8) * 255
            cnts, _ = cv2.findContours(mask, retr, chain)
            for c in cnts:
                area = cv2.contourArea(c)
                if area < min_area:
                    continue
                approx = cv2.approxPolyDP(c, eps, True)
                if len(approx) < 3:
                    continue
                d = "M " + " ".join(f"{p[0][0]},{p[0][1]}" for p in approx) + " Z"
                r, g, b = palette[lab]
                paths.append(f'<path d="{d}" fill="#{r:02x}{g:02x}{b:02x}"/>')
        return paths

    # First attempt (fast)
    paths = pass_once()
    # Fallbacks if nothing drew
    if len(paths) == 0:
        # try tree retrieval (captures holes)
        paths = pass_once(retr=cv2.RETR_TREE)
    if len(paths) == 0 and min_area_px > 1:
        # drop area threshold 10x
        paths = pass_once(min_area=max(1, int(min_area_px // 10)))
    if len(paths) == 0 and eps > 0.5:
        # reduce simplification
        eps_factor *= 0.5
        paths = pass_once()

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'preserveAspectRatio="xMidYMid meet">{"".join(paths)}</svg>'
    )
    return svg, len(paths)

# ---------- route ----------
@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(4),
    primitive_snap: bool = Form(False),
    smoothness: str = Form("medium"),        # "low"|"medium"|"high"
    min_path_area: float = Form(0.0005),     # fraction of W*H
    order: str = Form("dark_to_light")       # default dark->light to be visible
):
    data = await file.read()
    img = Image.open(io.BytesIO(data)).convert("RGB")
    W, H = img.size
    rgb = np.array(img)

    k = int(np.clip(max_colors, 2, 8))
    labels_img, palette = quantize_kmeans(rgb, k)

    eps_factor = 0.0015
    if smoothness == "low":   eps_factor = 0.0005
    if smoothness == "high":  eps_factor = 0.0025

    area_px = max(1, int(float(min_path_area) * (W * H)))

    svg, npaths = build_svg_from_labels(labels_img, palette, area_px, order, eps_factor)

    # attach a tiny debug header (shows up in Network tab)
    headers = {"X-Vectorize-Debug": f"paths={npaths}; area_px={area_px}; epsFactor={eps_factor}"}
    return JSONResponse({"svg": svg}, headers=headers)
