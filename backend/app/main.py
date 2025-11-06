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

# -------------------------- Health --------------------------

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return PlainTextResponse("ok")

# ----------------------- Utilities --------------------------

def srgb_to_linear(x: np.ndarray) -> np.ndarray:
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)

def linear_to_srgb(x: np.ndarray) -> np.ndarray:
    # avoid NaNs / negatives from tiny numeric errors
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

# ---------------- Reconstruction Scores ---------------------

def recon_error_bw(original_rgb: np.ndarray, mask: np.ndarray) -> float:
    """Edge-aware score for a B/W mask. Lower is better."""
    import cv2
    gray = cv2.cvtColor(original_rgb, cv2.COLOR_RGB2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    mag = cv2.normalize(mag, None, 0.0, 1.0, cv2.NORM_MINMAX)
    m = (mask.astype(np.float32) / 255.0)
    # Prefer covering edges; lightly penalize extra ink
    miss = np.maximum(mag - m, 0.0)
    extra = np.maximum(m - mag, 0.0)
    return float((miss.mean() * 0.8) + (extra.mean() * 0.2))

def recon_error_color(original_rgb: np.ndarray, labels_img: np.ndarray, palette: np.ndarray) -> float:
    """Grayscale MSE for a k-means quantized candidate. Lower is better."""
    import cv2
    H, W = labels_img.shape
    recon = palette[labels_img].reshape(H, W, 3).astype(np.uint8)
    r1 = cv2.cvtColor(recon, cv2.COLOR_RGB2GRAY).astype(np.float32)
    r2 = cv2.cvtColor(original_rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    return float(np.mean((r1 - r2) ** 2)) / (255.0 ** 2)

# --------------------- B/W Vectorization --------------------

def _contours_from_mask(mask, min_area_px, full_cut, eps_px):
    import cv2
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    paths = []
    kept = 0
    for c in cnts:
        area = cv2.contourArea(c)
        if area < min_area_px or area >= full_cut:
            continue
        approx = cv2.approxPolyDP(c, eps_px, True)
        if len(approx) < 3:
            continue
        d = "M " + " ".join(f"{p[0][0]},{p[0][1]}" for p in approx) + " Z"
        paths.append(d)
        kept += 1
    return kept, paths

def vectorize_bw_auto(rgb: np.ndarray, min_area_px: int, eps_px: float):
    """Try Otsu normal & inverted, score, and choose the better one."""
    import cv2

    H, W, _ = rgb.shape
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # both Otsu masks
    _, mask_norm = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)      # light foreground
    _, mask_inv  = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)  # dark foreground

    # light despeckle
    kernel = np.ones((2, 2), np.uint8)
    mask_norm = cv2.morphologyEx(mask_norm, cv2.MORPH_OPEN, kernel)
    mask_inv  = cv2.morphologyEx(mask_inv,  cv2.MORPH_OPEN, kernel)

    # score both masks
    err_norm = recon_error_bw(rgb, mask_norm)
    err_inv  = recon_error_bw(rgb, mask_inv)

    full_cut = 0.95 * (W * H)

    kept_norm, paths_norm = _contours_from_mask(mask_norm, min_area_px, full_cut, eps_px)
    kept_inv,  paths_inv  = _contours_from_mask(mask_inv,  min_area_px, full_cut, eps_px)

    # choose by score first, then by kept contours, tie-breaker prefers dark foreground
    if err_inv < err_norm:
        choose_inv = True
    elif err_inv > err_norm:
        choose_inv = False
    else:
        if kept_inv > kept_norm:
            choose_inv = True
        elif kept_inv < kept_norm:
            choose_inv = False
        else:
            choose_inv = True  # prefer dark ink on white

    paths = paths_inv if choose_inv else paths_norm
    fill_color = "#000000" if choose_inv else "#FFFFFF"

    # build SVG
    bg = f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>'
    svg_paths = "".join(f'<path d="{d}" fill="{fill_color}"/>' for d in paths)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">{bg}{svg_paths}</svg>'
    )
    return svg, len(paths)

# -------------------- Color Vectorization -------------------

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

    path_fragments = []
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
            path_fragments.append(f'<path d="{d}" fill="#{r:02x}{g:02x}{b:02x}"/>')

    bg = f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>'
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'preserveAspectRatio="xMidYMid meet">{bg}{"".join(path_fragments)}</svg>'
    )
    return svg, len(path_fragments)

# ------------------------- Endpoint -------------------------

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(4),
    primitive_snap: bool = Form(False),   # reserved for future use
    smoothness: str = Form("medium"),
    min_path_area: float = Form(0.0005),
    order: str = Form("dark_to_light")
):
    data = await file.read()
    rgb, (W, H) = image_to_np_rgb(data)

    diag = (W ** 2 + H ** 2) ** 0.5

    # simplification tolerance (px) tied to image size
    eps_factor = 0.0015
    if smoothness == "low":
        eps_factor = 0.0005
    elif smoothness == "high":
        eps_factor = 0.0025
    eps_px = float(np.clip(eps_factor * diag, 0.5, 0.05 * diag))

    # area threshold
    area_px = max(1, int(float(min_path_area) * (W * H)))

    # Heuristic: B/W if very low saturation OR requested colors <= 2
    sat = mean_saturation(rgb)
    use_bw = (int(max_colors) <= 2) or (sat < 0.10)

    if use_bw:
        svg, npaths = vectorize_bw_auto(rgb, area_px, eps_px)
        return JSONResponse({"svg": svg}, headers={
            "X-Mode": "bw-auto",
            "X-Paths": str(npaths)
        })

    # Auto-k for color (robust across varied designs)
    k_candidates = [2, 3, 4, 6]
    best = None
    for k_try in k_candidates:
        labels_img, palette = quantize_kmeans(rgb, k_try)
        err = recon_error_color(rgb, labels_img, palette)
        if (best is None) or (err < best["err"]):
            best = {"k": k_try, "labels": labels_img, "palette": palette, "err": err}

    svg, npaths = raster_to_svg_contours(best["labels"], best["palette"], area_px, order, eps_px)
    return JSONResponse({"svg": svg}, headers={
        "X-Mode": "kmeans",
        "X-K": str(best["k"]),
        "X-Error": f'{best["err"]:.6f}',
        "X-Paths": str(npaths)
    })
