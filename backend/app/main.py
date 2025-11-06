import io
import numpy as np
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response
from PIL import Image
import cv2


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
#  Contour With Holes
# =========================
def _contours_from_mask(mask, min_area_px, full_cut, eps_px):
    H, W = mask.shape[:2]
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return 0, []

    hier = hier[0]
    paths = []

    for i, c in enumerate(cnts):
        parent = hier[i][3]
        if parent != -1:
            continue

        area = cv2.contourArea(c)
        x, y, w, h = cv2.boundingRect(c)

        if area >= 0.98 * (W * H) or (w >= 0.98 * W and h >= 0.98 * H):
            continue
        if area < min_area_px or area >= full_cut:
            continue

        outer = cv2.approxPolyDP(c, eps_px, True)
        if len(outer) < 3:
            continue

        d = "M " + " ".join(f"{p[0][0]},{p[0][1]}" for p in outer) + " Z"

        child = hier[i][2]
        while child != -1:
            cc = cnts[child]
            c_area = cv2.contourArea(cc)
            if c_area >= min_area_px:
                approx = cv2.approxPolyDP(cc, eps_px, True)
                if len(approx) >= 3:
                    d += " M " + " ".join(f"{p[0][0]},{p[0][1]}" for p in approx) + " Z"
            child = hier[child][0]

        paths.append(d)

    return len(paths), paths


# =========================
# Auto B/W Vectorization
# =========================
def vectorize_bw_auto(rgb: np.ndarray, min_area_px: int, eps_px: float):
    H, W, _ = rgb.shape
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    full_cut = 0.95 * (W * H)

    # --- candidate masks ---
    _, m_norm = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, m_inv  = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    m_adp  = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 31, 5)
    m_adpi = cv2.bitwise_not(m_adp)

    kernel = np.ones((2, 2), np.uint8)
    masks = [
        ("otsu_norm", cv2.morphologyEx(m_norm, cv2.MORPH_OPEN, kernel)),
        ("otsu_inv",  cv2.morphologyEx(m_inv,  cv2.MORPH_OPEN, kernel)),
        ("adp_norm",  cv2.morphologyEx(m_adp,  cv2.MORPH_OPEN, kernel)),
        ("adp_inv",   cv2.morphologyEx(m_adpi, cv2.MORPH_OPEN, kernel)),
    ]

    def score(mask):
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        mag = cv2.normalize(mag, None, 0.0, 1.0, cv2.NORM_MINMAX)
        m = (mask.astype(np.float32) / 255.0)
        miss = np.maximum(mag - m, 0)
        extra = np.maximum(m - mag, 0)
        return float((miss.mean() * 0.8) + (extra.mean() * 0.2))

    scored = sorted(((n, m, score(m)) for n, m in masks), key=lambda x: x[2])

    # try best → worst
    for name, mask, _ in scored:
        inside = gray[mask > 0]
        outside = gray[mask == 0]
        if inside.size and outside.size and inside.mean() > outside.mean():
            mask = cv2.bitwise_not(mask)

        fg_ratio = float((mask > 0).mean())
        if fg_ratio > 0.98 or fg_ratio < 0.01:
            continue

        found, paths = _contours_from_mask(mask, min_area_px, full_cut, eps_px)
        if found > 0:
            break
    else:
        # last-ditch fallback: edges
        edges = cv2.Canny(gray, 80, 160)
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
        _, paths = _contours_from_mask(edges, 1, full_cut, eps_px)
        name = "canny_fallback"

    bg = f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>'
    svg_paths = "".join(
        f'<path d="{d}" fill="#000000" fill-rule="evenodd"/>' for d in paths
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">'
        f'{bg}{svg_paths}</svg>'
    )

    return svg, len(paths), name


# =========================
# API Endpoint
# =========================
@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(2),
    min_area_frac: float = Form(0.0002),
    primitive_snap: bool = Form(False),
):
    raw = await file.read()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    rgb = np.array(img)
    H, W = rgb.shape[:2]
    min_area_px = int(min_area_frac * H * W)
    eps_px = float(0.001 * max(H, W))

    svg, kept, mode = vectorize_bw_auto(rgb, min_area_px, eps_px)

    headers = {
        "X-Mode": "bw-auto",
        "X-BW": mode,
        "X-Paths": str(kept),
        "Content-Type": "image/svg+xml",
    }

    return Response(content=svg, headers=headers, media_type="image/svg+xml")


@app.get("/")
def root():
    return JSONResponse({"status": "ok", "service": "vectorizer"})
