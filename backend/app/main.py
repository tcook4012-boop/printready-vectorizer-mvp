# backend/app/main.py
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
import numpy as np
import cv2
from sklearn.cluster import KMeans
from io import BytesIO
from PIL import Image

app = FastAPI()

# allow your Vercel frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- helpers ----------

def _read_image(file_bytes: bytes) -> np.ndarray:
    # PIL ensures weird encodings still load; keep alpha if present then drop later
    img = Image.open(BytesIO(file_bytes)).convert("RGBA")
    # flatten alpha onto white to avoid holes in contours
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    img = Image.alpha_composite(bg, img).convert("RGB")
    arr = np.array(img)  # RGB
    return arr

def _resize_max(img: np.ndarray, max_side: int = 1600) -> tuple[np.ndarray, float]:
    h, w = img.shape[:2]
    scale = 1.0
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img, scale

def _to_svg_path(contour: np.ndarray, scale_back: float) -> str:
    # contour is Nx1x2 float/int; scale back to original pixels
    pts = contour.reshape(-1, 2) / scale_back
    # M x,y  L x,y ... Z
    cmds = []
    for i, (x, y) in enumerate(pts):
        if i == 0:
            cmds.append(f"M {x:.2f} {y:.2f}")
        else:
            cmds.append(f"L {x:.2f} {y:.2f}")
    cmds.append("Z")
    return " ".join(cmds)

def _smooth_epsilon(perimeter: float, smoothness: str) -> float:
    # match your UI dropdown
    s = (smoothness or "Low").lower()
    if "high" in s:
        frac = 0.01    # smoother curves, more simplification
    elif "medium" in s:
        frac = 0.005
    else:  # low (faster, sharper)
        frac = 0.0025
    return max(0.5, perimeter * frac)

def _binary_mask_from_gray(gray: np.ndarray) -> np.ndarray:
    # Otsu binarization (text/graphics friendly)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Detect background by sampling the border; if border is dark, invert so background is white
    border = np.concatenate([
        mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]
    ])
    border_dark_ratio = (border < 128).mean()
    if border_dark_ratio > 0.5:
        mask = 255 - mask

    # If mask is almost empty/full, fall back to adaptive
    white_ratio = (mask > 128).mean()
    if white_ratio < 0.02 or white_ratio > 0.98:
        adap = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 5
        )
        # choose the variant whose border looks white
        border2 = np.concatenate([adap[0, :], adap[-1, :], adap[:, 0], adap[:, -1]])
        if (border2 < 128).mean() <= 0.5:
            mask = adap

    return mask

def _quantize_lab(img_rgb: np.ndarray, k: int, rnd: int = 0) -> tuple[np.ndarray, np.ndarray]:
    # Convert RGB to Lab for perceptual clustering
    img_lab = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2LAB)
    h, w = img_lab.shape[:2]
    flat = img_lab.reshape(-1, 3).astype(np.float32)

    kmeans = KMeans(n_clusters=k, n_init=4, random_state=rnd, max_iter=200)
    labels = kmeans.fit_predict(flat)
    centers = kmeans.cluster_centers_.astype(np.float32)

    # back to RGB palette for rendering
    centers_lab = centers.reshape(-1, 1, 3)
    centers_rgb = cv2.cvtColor(centers_lab, cv2.COLOR_Lab2RGB).reshape(-1, 3)
    centers_rgb = np.clip(centers_rgb, 0, 255).astype(np.uint8)

    label_img = labels.reshape(h, w)
    return label_img, centers_rgb

def _layer_order_indices(centers_rgb: np.ndarray, order: str) -> list[int]:
    # Order by luminance (Y’ from Rec.601)
    def luma(c):
        r, g, b = c
        return 0.299 * r + 0.587 * g + 0.114 * b

    idxs = list(range(len(centers_rgb)))
    idxs.sort(key=lambda i: luma(centers_rgb[i]), reverse=("dark" in (order or "").lower()))
    return idxs

# ---------- SVG builders ----------

def _svg_header(w: int, h: int) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" shape-rendering="geometricPrecision">'

def _svg_footer() -> str:
    return "</svg>"

def _svg_color(rgb: np.ndarray) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

def _contours_to_paths(mask: np.ndarray, min_area_px: float, smoothness: str, scale_back: float) -> list[str]:
    # Extract contours (external + holes)
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    paths = []
    if hierarchy is None:
        return paths

    h = hierarchy[0]
    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        if area < min_area_px:
            continue
        eps = _smooth_epsilon(cv2.arcLength(cnt, True), smoothness)
        approx = cv2.approxPolyDP(cnt, eps, True)
        d = _to_svg_path(approx, scale_back)

        # holes: draw as separate paths with fill-rule evenodd
        # We’ll just use one path per contour; fill-rule evenodd on group handles holes.
        paths.append(d)
    return paths

# ---------- API ----------

@app.get("/")
def health():
    return PlainTextResponse("OK")

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(2),
    primitive_snap: bool = Form(False),   # accepted but not used in this baseline
    smoothness: str = Form("Low (faster, sharper)"),
    min_path_area: float = Form(0.0002),  # fraction of pixels
    layer_order: str = Form("Dark → Light"),  # or "Light → Dark"
):
    data = await file.read()
    rgb = _read_image(data)  # RGB
    rgb, scale = _resize_max(rgb, 1600)
    h, w = rgb.shape[:2]
    total_px = h * w
    min_area_px = max(1.0, min_path_area * total_px)

    svg_parts = [_svg_header(w / scale, h / scale)]

    if max_colors <= 2:
        # --- Binary mode (two colors: black & white) ---
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        mask_white = _binary_mask_from_gray(gray)  # 255=white background, 0=black ink if text is dark

        # Build two layers: background (white) then foreground (black)
        # Background rectangle:
        svg_parts.append(f'<rect x="0" y="0" width="{w/scale:.2f}" height="{h/scale:.2f}" fill="#ffffff"/>')

        # Foreground mask is the inverse of white areas:
        mask_black = (mask_white < 128).astype(np.uint8) * 255
        paths = _contours_to_paths(mask_black, min_area_px, smoothness, scale)
        if paths:
            svg_parts.append('<g fill="#000000" stroke="none" fill-rule="evenodd">')
            for d in paths:
                svg_parts.append(f'<path d="{d}"/>')
            svg_parts.append('</g>')
    else:
        # --- Multi-color mode (3–8 colors) ---
        label_img, palette = _quantize_lab(rgb, int(max_colors), rnd=0)
        order = _layer_order_indices(palette, layer_order)

        # Draw background layer first: pick the lightest/darkest per order
        for idx in order:
            col = palette[idx]
            mask = (label_img == idx).astype(np.uint8) * 255
            # filter tiny specks (open-close)
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

            paths = _contours_to_paths(mask, min_area_px, smoothness, scale)
            if not paths:
                continue
            fill = _svg_color(col)
            svg_parts.append(f'<g fill="{fill}" stroke="none" fill-rule="evenodd">')
            for d in paths:
                svg_parts.append(f'<path d="{d}"/>')
            svg_parts.append('</g>')

    svg_parts.append(_svg_footer())
    svg = "".join(svg_parts)

    return JSONResponse({"svg": svg})
