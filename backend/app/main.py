# backend/app/main.py
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Tuple
import io
import numpy as np
from PIL import Image
import cv2

app = FastAPI(title="PrintReady Vectorizer API", version="0.3")

# CORS for your Vercel app and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- small utils ----------

def clamp01(x: np.ndarray) -> np.ndarray:
    return np.minimum(1.0, np.maximum(0.0, x))

def to_hex(rgb01: np.ndarray) -> str:
    rgb255 = (clamp01(rgb01) * 255.0 + 0.5).astype(np.uint8)
    return "#{:02x}{:02x}{:02x}".format(int(rgb255[0]), int(rgb255[1]), int(rgb255[2]))

def luminance(rgb01: np.ndarray) -> float:
    # sRGB luma approximation
    r, g, b = rgb01
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def order_palette(palette01: List[np.ndarray], layer_order: str) -> List[np.ndarray]:
    # sort by luminance then order
    palette01 = list(palette01)
    palette01.sort(key=lambda c: luminance(c))
    if layer_order == "light_to_dark":
        palette01.reverse()
    return palette01

def find_paths_from_mask(mask: np.ndarray, min_area_px: float) -> List[str]:
    # mask: uint8 0/255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    paths = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area_px:
            continue
        if len(cnt) < 3:
            continue
        # Simplify a bit to reduce noisy points
        epsilon = 0.0025 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        if len(approx) < 3:
            continue
        # SVG path from polygon
        coords = approx[:, 0, :]  # (N,2)
        d = f"M {coords[0,0]} {coords[0,1]}"
        for x, y in coords[1:]:
            d += f" L {x} {y}"
        d += " Z"
        paths.append(d)
    return paths

def svg_from_layers(width: int, height: int, layers: List[Tuple[str, List[str]]]) -> str:
    # layers: list of (fill_hex, [path_d, ...]) drawn in order (bottom -> top)
    viewbox = f'viewBox="0 0 {width} {height}"'
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" {viewbox} width="{width}" height="{height}" preserveAspectRatio="xMidYMid meet">']
    for fill_hex, paths in layers:
        if not paths:
            continue
        for d in paths:
            parts.append(f'<path d="{d}" fill="{fill_hex}" />')
    parts.append("</svg>")
    return "\n".join(parts)

# ---------- color quantization ----------

def kmeans_palette(rgb: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    rgb: HxWx3, uint8
    returns: (labels HxW int, centers kx3 uint8)
    """
    h, w, _ = rgb.shape
    flat = rgb.reshape(-1, 3).astype(np.float32)

    # k-means
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    attempts = 1
    flags = cv2.KMEANS_PP_CENTERS
    compactness, labels, centers = cv2.kmeans(flat, k, None, criteria, attempts, flags)
    labels = labels.reshape(h, w).astype(np.int32)
    centers = centers.astype(np.uint8)
    return labels, centers

def threshold_two_tone(rgb: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    For 2 colors: robust Otsu threshold on gray to split into two fills.
    Returns: labels HxW in {0,1}, and palette (2,3) uint8 (darker first).
    """
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # Otsu
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # mask==255 is light; define darker = 0, lighter = 1
    labels = (mask // 255).astype(np.int32)

    # Estimate the two colors as medians from each region (in RGB)
    dark_vals = rgb[labels == 0]
    light_vals = rgb[labels == 1]
    if len(dark_vals) == 0:
        dark_c = np.array([0, 0, 0], dtype=np.uint8)
    else:
        dark_c = np.median(dark_vals, axis=0).astype(np.uint8)
    if len(light_vals) == 0:
        light_c = np.array([255, 255, 255], dtype=np.uint8)
    else:
        light_c = np.median(light_vals, axis=0).astype(np.uint8)

    # Make sure dark is visually darker than light
    if luminance(dark_c / 255.0) > luminance(light_c / 255.0):
        # swap
        labels = 1 - labels
        dark_c, light_c = light_c, dark_c

    centers = np.vstack([dark_c, light_c])  # [0]=dark, [1]=light
    return labels, centers

# ---------- endpoints ----------

@app.get("/")
def health():
    return {"status": "ok", "service": "vectorizer"}

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    # new field names
    max_colors: int = Form(2),
    primitive_snap: str = Form("false"),
    min_area_frac: float = Form(None),         # NEW preferred
    layer_order: str = Form(None),             # NEW preferred
    # legacy fallbacks (belt & suspenders)
    maxColors: int = Form(None),
    primitiveSnap: str = Form(None),
    minPathArea: float = Form(None),
    order: str = Form(None),
):
    """
    Returns JSON: { "svg": "<svg ...>" }
    """

    # ---- compatibility shim ----
    if maxColors is not None:
        max_colors = maxColors
    if primitiveSnap is not None:
        primitive_snap = primitiveSnap
    if min_area_frac is None and minPathArea is not None:
        min_area_frac = minPathArea
    if layer_order is None and order is not None:
        o = (order or "").lower()
        if "dark" in o and "light" in o and "→" in o:
            # UI may send e.g. "Light → Dark" (don’t rely on this though)
            layer_order = "light_to_dark" if o.startswith("light") else "dark_to_light"
        elif "light_to_dark" in o or "light -> dark" in o:
            layer_order = "light_to_dark"
        elif "dark_to_light" in o or "dark -> light" in o:
            layer_order = "dark_to_light"

    # sane defaults if still missing
    max_colors = int(max(2, min(8, max_colors or 2)))
    primitive_snap = str(primitive_snap).lower() == "true"
    if min_area_frac is None:
        min_area_frac = 0.0002
    if layer_order not in ("light_to_dark", "dark_to_light"):
        layer_order = "light_to_dark"

    # ---- read image ----
    raw = await file.read()
    try:
        pil = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return JSONResponse({"error": "Unsupported image"}, status_code=400)

    rgb = np.array(pil)  # HxWx3 uint8
    h, w, _ = rgb.shape
    total_px = float(h * w)
    min_area_px = float(min_area_frac) * total_px

    # ---- quantize to labels + centers ----
    if max_colors <= 2:
        labels, centers = threshold_two_tone(rgb)
    else:
        labels, centers = kmeans_palette(rgb, max_colors)

    # centers: kx3 uint8 -> convert to 0..1 for ordering + hex
    palette01 = [(c.astype(np.float32) / 255.0) for c in centers]
    # Order palette by requested layer order
    ordered = order_palette(palette01, layer_order=layer_order)

    # Build mapping from ordered palette -> masks
    # We map each pixel's center to its ordered rank.
    # First compute luminance ranks of original centers
    center_lums = [luminance(c) for c in palette01]
    idx_sorted = np.argsort(center_lums)  # dark -> light
    if layer_order == "light_to_dark":
        idx_sorted = idx_sorted[::-1]     # light -> dark

    # For each rank in the chosen order, collect a mask of pixels that belong to that center
    layers: List[Tuple[str, List[str]]] = []
    for rank, center_idx in enumerate(idx_sorted):
        center_rgb01 = palette01[center_idx]
        fill_hex = to_hex(center_rgb01)

        mask = (labels == int(center_idx)).astype(np.uint8) * 255
        paths = find_paths_from_mask(mask, min_area_px=min_area_px)
        layers.append((fill_hex, paths))

    # Compose final SVG (bottom -> top is current order in 'layers')
    svg = svg_from_layers(w, h, layers)
    return {"svg": svg}
