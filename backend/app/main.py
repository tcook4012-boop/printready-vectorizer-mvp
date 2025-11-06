# backend/app/main.py
# Hardened vectorizer API focused on 2–3 color signage/text.
# Inputs: multipart/form-data: file + options (strings)
# Output: JSON {"svg": "<svg ...>"}

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import cv2
from io import BytesIO
from PIL import Image
import json
import math

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ---------- helpers

def pil_to_bgr(img_pil: Image.Image) -> np.ndarray:
    if img_pil.mode != "RGB":
        img_pil = img_pil.convert("RGB")
    arr = np.asarray(img_pil)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

def bgr_to_rgb(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

def clip01(x):
    return np.clip(x, 0.0, 1.0)

def img_border_mask(h, w, border=0.04):
    t = max(1, int(border * min(h, w)))
    m = np.zeros((h, w), np.uint8)
    m[:t, :] = 1; m[-t:, :] = 1; m[:, :t] = 1; m[:, -t:] = 1
    return m.astype(bool)

def auto_background_is_light(bgr: np.ndarray) -> bool:
    # Decide if page background is light using border V channel mean
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    v  = hsv[:, :, 2]
    mask = img_border_mask(*v.shape)
    return float(v[mask].mean()) >= 128.0

def apply_clahe_on_v(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    v2 = clahe.apply(v)
    hsv[:, :, 2] = v2
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

def morph_cleanup(mask: np.ndarray, min_path_area_frac: float) -> np.ndarray:
    # Kernel size proportional to image and target area
    h, w = mask.shape
    target_px = max(1, int(min_path_area_frac * (h * w)))
    # derive side length ~ sqrt(target_px) but clamped
    k = int(max(1, round(math.sqrt(target_px) * 0.5)))
    k = int(np.clip(k, 1, max(3, min(h, w)//150)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*k+1, 2*k+1))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel)
    return cleaned

def contours_to_svg_path(contours, simplify_eps):
    # Build one path string from many contours; use absolute M/L for robustness.
    parts = []
    for c in contours:
        if len(c) < 2: 
            continue
        if simplify_eps > 0 and len(c) >= 3:
            c = cv2.approxPolyDP(c, simplify_eps, True)
        pts = c.reshape(-1, 2)
        # move-to first
        parts.append(f"M {pts[0,0]} {pts[0,1]}")
        # line-to rest
        for p in pts[1:]:
            parts.append(f"L {p[0]} {p[1]}")
        parts.append("Z")
    return " ".join(parts)

def make_svg_header(w, h):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'

def wrap_svg(svg_inner):
    return svg_inner + "</svg>"

def kmeans_lab(bgr: np.ndarray, k: int):
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    h, w, _ = lab.shape
    data = lab.reshape(-1, 3).astype(np.float32)

    # prefer seeding white/black if k>=2
    term = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    flags = cv2.KMEANS_PP_CENTERS
    compactness, labels, centers = cv2.kmeans(data, k, None, term, 3, flags)

    labels = labels.reshape(h, w)
    centers = centers.astype(np.uint8)
    return labels, centers  # in Lab

def lab_to_bgr_color(Lab):
    color = np.uint8([[Lab]])
    bgr = cv2.cvtColor(color, cv2.COLOR_LAB2BGR)[0,0]
    return int(bgr[0]), int(bgr[1]), int(bgr[2])

def luminance_of_bgr(bgr):
    # sRGB luminance proxy
    r, g, b = bgr[2]/255.0, bgr[1]/255.0, bgr[0]/255.0
    return 0.2126*r + 0.7152*g + 0.0722*b

# ---------- vectorization strategies

def vectorize_two_color(bgr: np.ndarray, min_path_area: float, smoothness: str, order: str) -> str:
    """
    Two-color: background (white) + foreground (black).
    Robust binarization + cleanup + trace to single black path.
    """
    h, w, _ = bgr.shape
    # improve separation
    bgr2 = apply_clahe_on_v(bgr)

    # OTSU on V channel
    hsv = cv2.cvtColor(bgr2, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    _, thr = cv2.threshold(v, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # ensure white background
    bg_is_light = auto_background_is_light(bgr)
    # thr==255 currently marks "light". If bg is light, background should be white (255).
    # If bg_is_light and the border is mostly black in thr, invert.
    border = img_border_mask(h, w)
    light_ratio_on_border = float((thr[border] > 0).mean())
    if bg_is_light and light_ratio_on_border < 0.5:
        thr = cv2.bitwise_not(thr)
    if not bg_is_light and light_ratio_on_border > 0.5:
        thr = cv2.bitwise_not(thr)

    # cleanup tiny specks
    thr = morph_cleanup(thr, min_path_area)

    # We want black shapes on white background:
    # Convert mask to 1 for foreground pixels (non-background)
    # Detect which side is foreground by choosing the minority class.
    white_count = int((thr == 255).sum())
    black_count = thr.size - white_count
    # If white dominates border, treat white as background.
    # Foreground mask should be the opposite class
    if white_count >= black_count:
        fg = (thr == 0).astype(np.uint8) * 255
    else:
        fg = (thr == 255).astype(np.uint8) * 255

    # Find contours of foreground
    contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # simplify by smoothness
    perim_avg = np.mean([cv2.arcLength(c, True) for c in contours]) if contours else 0
    # smaller eps = sharper. “low” -> 0.5% perim, “medium” 1.0%, “high” 1.5%
    if smoothness == "high":   frac = 0.015
    elif smoothness == "medium": frac = 0.010
    else:                      frac = 0.005
    simplify_eps = float(frac * perim_avg)

    path_d = contours_to_svg_path(contours, simplify_eps)

    svg = [make_svg_header(w, h)]
    svg.append('<rect x="0" y="0" width="100%" height="100%" fill="#ffffff"/>')
    if path_d:
        svg.append(f'<path d="{path_d}" fill="#000000" stroke="none"/>')
    return wrap_svg("".join(svg))

def vectorize_kmeans(bgr: np.ndarray, k: int, min_path_area: float, smoothness: str, order: str) -> str:
    """
    3–8 colors: k-means in Lab, order by luminance, separate contours per color.
    """
    h, w, _ = bgr.shape
    bgr2 = apply_clahe_on_v(bgr)
    labels, centers_lab = kmeans_lab(bgr2, k)

    # Convert centers to BGR and sort by luminance
    palette = []
    for i, lab in enumerate(centers_lab):
        b, g, r = lab_to_bgr_color(lab)
        palette.append((i, (b, g, r), luminance_of_bgr((b, g, r))))
    palette.sort(key=lambda x: x[2])  # dark -> light
    if order == "light_to_dark":
        palette.reverse()

    # build SVG
    svg = [make_svg_header(w, h)]
    # ensure background is the lightest color (rough heuristic):
    bg_idx = palette[0][0] if order == "light_to_dark" else palette[-1][0]
    bg_bgr = palette[0][1] if order == "light_to_dark" else palette[-1][1]
    svg.append(f'<rect x="0" y="0" width="100%" height="100%" fill="rgb({bg_bgr[2]},{bg_bgr[1]},{bg_bgr[0]})"/>')

    # trace each color layer
    perim_eps_base = 0.01 if smoothness == "medium" else (0.015 if smoothness == "high" else 0.005)

    for idx, color_bgr, _lum in palette:
        mask = (labels == idx).astype(np.uint8) * 255
        mask = morph_cleanup(mask, min_path_area)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        perim_avg = np.mean([cv2.arcLength(c, True) for c in contours])
        simplify_eps = float(perim_avg * perim_eps_base)

        d = contours_to_svg_path(contours, simplify_eps)
        if not d:
            continue
        r, g, b = color_bgr[2], color_bgr[1], color_bgr[0]
        svg.append(f'<path d="{d}" fill="rgb({r},{g},{b})" stroke="none"/>')

    return wrap_svg("".join(svg))

# ---------- FastAPI endpoints

@app.get("/", response_class=PlainTextResponse)
def root():
    return "PrintReady Vectorizer API"

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: str = Form("2"),
    smoothness: str = Form("low"),           # "low"|"medium"|"high"
    primitive_snap: str = Form("false"),
    min_path_area: str = Form("0.0002"),     # fraction of pixels
    order: str = Form("light_to_dark")       # "light_to_dark"|"dark_to_light"
):
    data = await file.read()
    img = Image.open(BytesIO(data))
    bgr = pil_to_bgr(img)

    try:
        k = int(max_colors)
    except:
        k = 2
    k = int(np.clip(k, 2, 8))

    try:
        mpa = float(min_path_area)
    except:
        mpa = 0.0002
    mpa = float(np.clip(mpa, 0.00001, 0.01))

    smoothness = (smoothness or "low").lower().strip()
    if smoothness not in ("low", "medium", "high"):
        smoothness = "low"

    order = (order or "light_to_dark").lower().strip()
    if order not in ("light_to_dark", "dark_to_light"):
        order = "light_to_dark"

    # route
    if k == 2:
        svg = vectorize_two_color(bgr, mpa, smoothness, order)
    else:
        svg = vectorize_kmeans(bgr, k, mpa, smoothness, order)

    return {"svg": svg}
