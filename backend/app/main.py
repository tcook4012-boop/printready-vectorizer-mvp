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
    x = np.nan_to_num(x, nan=0.0)
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * (x ** (1.0 / 2.4)) - 0.055)

def image_to_np_rgb(data: bytes):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return np.array(img), img.size  # (H,W,3), (W,H)

def mean_saturation(rgb: np.ndarray) -> float:
    arr = rgb.astype(np.float32) / 255.0
    mx = arr.max(axis=2); mn = arr.min(axis=2)
    sat = np.zeros_like(mx)
    mask = mx > 0
    sat[mask] = (mx[mask] - mn[mask]) / mx[mask]
    return float(sat.mean())

# ---------------- Reconstruction Scores ---------------------

def recon_error_bw(original_rgb: np.ndarray, mask: np.ndarray) -> float:
    """Edge-aware score for BW candidates. Lower is better."""
    import cv2
    gray = cv2.cvtColor(original_rgb, cv2.COLOR_RGB2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    mag = cv2.normalize(mag, None, 0.0, 1.0, cv2.NORM_MINMAX)
    m = (mask.astype(np.float32) / 255.0)
    miss = np.maximum(mag - m, 0.0)
    extra = np.maximum(m - mag, 0.0)
    return float((miss.mean() * 0.8) + (extra.mean() * 0.2))

def recon_error_color(original_rgb: np.ndarray, labels_img: np.ndarray, palette: np.ndarray) -> float:
    """Grayscale MSE for a k-means candidate. Lower is better."""
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
    paths = []; kept = 0
    for c in cnts:
        area = cv2.contourArea(c)
        if area < min_area_px or area >= full_cut:
            continue
        approx = cv2.approxPolyDP(c, eps_px, True)
        if len(approx) < 3:
            continue
        d = "M " + " ".join(f"{p[0][0]},{p[0][1]}" for p in approx) + " Z"
        paths.append(d); kept += 1
    return kept, paths

def _bw_candidates(rgb):
    """Return list of (name, mask) candidates to try."""
    import cv2
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # Otsu normal/inverted
    _, m_norm = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, m_inv  = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Adaptive Gaussian normal/inverted (helps uneven backgrounds)
    m_adp  = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 31, 5)
    m_adpi = cv2.bitwise_not(m_adp)

    kernel = np.ones((2, 2), np.uint8)
    cands = [
        ("otsu_norm", cv2.morphologyEx(m_norm, cv2.MORPH_OPEN, kernel)),
        ("otsu_inv",  cv2.morphologyEx(m_inv,  cv2.MORPH_OPEN, kernel)),
        ("adp_norm",  cv2.morphologyEx(m_adp,  cv2.MORPH_OPEN, kernel)),
        ("adp_inv",   cv2.morphologyEx(m_adpi, cv2.MORPH_OPEN, kernel)),
    ]
    return cands

def _ensure_dark_foreground(rgb, mask):
    """If the chosen mask selects light ink, invert it so foreground is dark."""
    import cv2
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    inside  = gray[mask > 0]
    outside = gray[mask == 0]
    if inside.size == 0 or outside.size == 0:
        return mask, True  # trivial; treat as dark
    # If inside is lighter than outside, invert to make ink dark
    if float(inside.mean()) > float(outside.mean()):
        mask = cv2.bitwise_not(mask)
    return mask, True  # after this, foreground is dark

def vectorize_bw_auto(rgb: np.ndarray, min_area_px: int, eps_px: float):
    import cv2
    H, W, _ = rgb.shape
    candidates = _bw_candidates(rgb)

    # Score and pick the best mask
    scored = [(name, mask, recon_error_bw(rgb, mask)) for name, mask in candidates]
    scored.sort(key=lambda t: t[2])  # lower error is better
    name, best_mask, _ = scored[0]

    # Make sure ink is dark; invert if necessary
    mask_dark, _ = _ensure_dark_foreground(rgb, best_mask)

    full_cut = 0.95 * (W * H)
    kept, paths = _contours_from_mask(mask_dark, min_area_px, full_cut, eps_px)

    # Fallback: if we got zero paths, try a Canny outline vector
    if kept == 0:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 80, 160)
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
        kept, paths = _contours_from_mask(edges, 1, full_cut, eps_px)  # allow tiny areas

    bg = f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>'
    svg_paths = "".join(f'<path d="{d}" fill="#000000"/>' for d in paths)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">{bg}{svg_paths}</svg>'
    )
    return svg, len(paths), name

# -------------------- Color Vectorization -------------------

def quantize_kmeans(rgb: np.ndarray, k: int):
    """Edge-preserving prefilter + k-means in linear RGB."""
    import cv2
    # Bilateral to reduce blotchiness while preserving edges
    pre = cv2.bilateralFilter(rgb, d=5, sigmaColor=50, sigmaSpace=5)
    arr = pre.astype(np.float32) / 255.0
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

    frags = []
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
            frags.append(f'<path d="{d}" fill="#{r:02x}{g:02x}{b:02x}"/>')

    bg = f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>'
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'preserveAspectRatio="xMidYMid meet">{bg}{"".join(frags)}</svg>'
    )
    return svg, len(frags)

# ------------------------- Endpoint -------------------------

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
    # simplification tolerance (px) tied to size
    eps_factor = 0.0015
    if smoothness == "low":   eps_factor = 0.0005
    elif smoothness == "high": eps_factor = 0.0025
    eps_px = float(np.clip(eps_factor * diag, 0.5, 0.05 * diag))

    area_px = max(1, int(float(min_path_area) * (W * H)))

    sat = mean_saturation(rgb)
    use_bw = (int(max_colors) <= 2) or (sat < 0.10)

    if use_bw:
        svg, npaths, bw_name = vectorize_bw_auto(rgb, area_px, eps_px)
        return JSONResponse({"svg": svg}, headers={
            "X-Mode": "bw-auto",
            "X-BW": bw_name,
            "X-Paths": str(npaths)
        })

    # Auto-k for color
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
