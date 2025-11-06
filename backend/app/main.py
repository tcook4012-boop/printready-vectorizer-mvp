import io
import numpy as np
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
import cv2


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Utilities
# ----------------------------
def rgb_to_hex(c):
    r, g, b = [int(np.clip(x, 0, 255)) for x in c]
    return f"#{r:02X}{g:02X}{b:02X}"

def rgb_luminance(c):
    # perceptual luminance from sRGB
    r, g, b = [x / 255.0 for x in c]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def approx_contour(contour, eps_px):
    return cv2.approxPolyDP(contour, eps_px, True)

def find_filled_paths(mask, min_area_px, eps_px, full_cut):
    """
    Vectorize a binary mask into even-odd filled path 'd' strings.
    Uses RETR_CCOMP to capture holes correctly.
    """
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return []

    hier = hier[0]
    paths = []

    for i, c in enumerate(cnts):
        # only process top-level; holes will be stitched as subpaths
        if hier[i][3] != -1:
            continue

        area = cv2.contourArea(c)
        if area < min_area_px or area >= full_cut:
            continue

        outer = approx_contour(c, eps_px)
        if outer is None or len(outer) < 3:
            continue

        d = "M " + " ".join(f"{p[0][0]},{p[0][1]}" for p in outer) + " Z"

        # stitch holes
        child = hier[i][2]
        while child != -1:
            cc = cnts[child]
            c_area = cv2.contourArea(cc)
            if c_area >= min_area_px:
                hole = approx_contour(cc, eps_px)
                if hole is not None and len(hole) >= 3:
                    d += " M " + " ".join(f"{p[0][0]},{p[0][1]}" for p in hole) + " Z"
            child = hier[child][0]

        paths.append(d)

    return paths

# ----------------------------
# B/W auto (fallback)
# ----------------------------
def vectorize_bw_auto(rgb, min_area_px, eps_px):
    H, W, _ = rgb.shape
    full_cut = 0.95 * (W * H)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # try multiple thresholds
    _, m_norm = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, m_inv  = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    m_adp  = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 31, 5)
    m_adpi = cv2.bitwise_not(m_adp)

    k = np.ones((2, 2), np.uint8)
    candidates = [
        ("otsu_norm", cv2.morphologyEx(m_norm, cv2.MORPH_OPEN, k)),
        ("otsu_inv",  cv2.morphologyEx(m_inv,  cv2.MORPH_OPEN, k)),
        ("adp_norm",  cv2.morphologyEx(m_adp,  cv2.MORPH_OPEN, k)),
        ("adp_inv",   cv2.morphologyEx(m_adpi, cv2.MORPH_OPEN, k)),
    ]

    # prefer mask with balanced foreground
    chosen = None
    for name, mask in candidates:
        fg_ratio = float((mask > 0).mean())
        if 0.02 < fg_ratio < 0.98:
            chosen = (name, mask)
            break

    mode = "bw_otsu"
    if chosen:
        name, mask = chosen
        # ensure dark ink is foreground
        inside = gray[mask > 0]
        outside = gray[mask == 0]
        if inside.size and outside.size and inside.mean() > outside.mean():
            mask = cv2.bitwise_not(mask)
        mode = name
        paths = find_filled_paths(mask, min_area_px, eps_px, full_cut)
    else:
        # last-ditch edges
        edges = cv2.Canny(gray, 80, 160)
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
        paths = find_filled_paths(edges, 1, eps_px, full_cut)
        mode = "bw_canny_fallback"

    svg = compose_svg(H, W, [("#000000", paths)], add_white_bg=True)
    return svg, len(paths), mode

# ----------------------------
# Multi-color vectorization
# ----------------------------
def kmeans_palette(rgb, k):
    """
    Quantize to k colors in CIELAB (better clustering).
    Returns labels (HxW) and palette colors in RGB uint8.
    """
    H, W, _ = rgb.shape
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5)
    ret, labels, centers = cv2.kmeans(
        lab, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )
    labels = labels.reshape(H, W)
    centers = centers.astype(np.uint8).reshape(k, 1, 1, 3)
    # back to RGB for display/fills
    colors_rgb = cv2.cvtColor(centers, cv2.COLOR_Lab2RGB).reshape(k, 3).astype(np.uint8)
    return labels, colors_rgb

def compose_svg(H, W, color_paths, add_white_bg=True):
    """
    color_paths: list of (hex_color, [path_d, ...])
    """
    bg = f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>' if add_white_bg else ""
    layers = []
    for hex_color, paths in color_paths:
        if not paths:
            continue
        layers.append(
            "".join(f'<path d="{d}" fill="{hex_color}" fill-rule="evenodd"/>' for d in paths)
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">'
        f'{bg}{"".join(layers)}</svg>'
    )
    return svg

def vectorize_multicolor(rgb, k, min_area_px, eps_px, layer_order="light_to_dark"):
    """
    Vectorize by color cluster; returns SVG with filled layers.
    """
    H, W, _ = rgb.shape
    full_cut = 0.95 * (W * H)

    labels, colors_rgb = kmeans_palette(rgb, k)

    # Build (color, paths) for each cluster
    clusters = []
    for idx in range(colors_rgb.shape[0]):
        mask = np.where(labels == idx, 255, 0).astype(np.uint8)

        # Clean up small noise, close thin gaps
        mask = cv2.medianBlur(mask, 3)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))

        paths = find_filled_paths(mask, min_area_px, eps_px, full_cut)
        hex_color = rgb_to_hex(colors_rgb[idx])
        lumin = rgb_luminance(colors_rgb[idx])
        clusters.append({"hex": hex_color, "paths": paths, "lumin": lumin})

    # If k=2 and both colors are very similar (degenerate), prefer BW auto
    if k == 2:
        c0, c1 = colors_rgb[0].astype(int), colors_rgb[1].astype(int)
        if np.linalg.norm(c0 - c1) < 12:  # very close
            return vectorize_bw_auto(rgb, min_area_px, eps_px)

    # sort by luminance
    rev = (layer_order == "dark_to_light")
    clusters.sort(key=lambda c: c["lumin"], reverse=rev)

    color_paths = [(c["hex"], c["paths"]) for c in clusters]
    svg = compose_svg(H, W, color_paths, add_white_bg=True)
    total_paths = sum(len(c["paths"]) for c in clusters)
    return svg, total_paths, "kmeans_lab"

# ----------------------------
# API
# ----------------------------
@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(2),
    min_area_frac: float = Form(0.0002),
    primitive_snap: bool = Form(False),  # currently unused but kept for API stability
    layer_order: str = Form("light_to_dark"),  # "light_to_dark" | "dark_to_light"
):
    raw = await file.read()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    rgb = np.array(img)

    H, W = rgb.shape[:2]
    min_area_px = max(1, int(min_area_frac * H * W))
    eps_px = float(0.001 * max(H, W))  # simplify ratio tied to image diagonal

    max_colors = int(np.clip(max_colors, 2, 8))

    # Multi-color path
    svg, kept, mode = vectorize_multicolor(
        rgb, max_colors, min_area_px, eps_px, layer_order=layer_order
    )

    # If nothing meaningful, fallback to B/W auto
    if kept == 0:
        svg, kept, mode = vectorize_bw_auto(rgb, min_area_px, eps_px)

    headers = {"X-Mode": mode, "X-Paths": str(kept)}
    return JSONResponse(content={"svg": svg}, headers=headers)

@app.get("/")
def root():
    return JSONResponse({"status": "ok", "service": "vectorizer"})
