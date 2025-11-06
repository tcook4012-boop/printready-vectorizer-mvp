# backend/app/main.py  (or backend/main.py depending on your layout)

import io
import math
from typing import List, Tuple

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="PrintReady Vectorizer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- helpers ----------

def to_rgb(img_bgr: np.ndarray) -> np.ndarray:
    if img_bgr.ndim == 2:
        img_bgr = cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2BGR)
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

def roughly_monochrome(rgb: np.ndarray, tol: float = 0.015) -> bool:
    ch = [rgb[..., 0], rgb[..., 1], rgb[..., 2]]
    stds = [np.std(c.astype(np.float32)/255.0) for c in ch]
    return max(stds) < tol

def auto_bg_fg(rgb: np.ndarray) -> Tuple[int, int]:
    # kmeans to 3 clusters; pick largest cluster as background, darkest as foreground
    Z = rgb.reshape(-1, 3).astype(np.float32)
    K = 3
    _, labels, centers = cv2.kmeans(
        Z, K, None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.2),
        2,
        cv2.KMEANS_PP_CENTERS
    )
    centers = centers.astype(np.float32)
    labels = labels.reshape(-1)
    counts = np.bincount(labels, minlength=K)
    bg_idx = int(np.argmax(counts))
    luma = (0.2126*centers[:,0] + 0.7152*centers[:,1] + 0.0722*centers[:,2])
    fg_idx = int(np.argmin(luma))
    return bg_idx, fg_idx

def vectorize_core(
    rgb: np.ndarray,
    max_colors: int,
    primitive_snap: bool,
    min_area_frac: float,
    layer_order: str
) -> str:
    h, w = rgb.shape[:2]

    # If nearly monochrome, simplify to black/white first
    if roughly_monochrome(rgb):
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU | cv2.THRESH_BINARY)[1]
        palette = np.array([[0,0,0], [255,255,255]], dtype=np.uint8)
        labels = (thr == 0).astype(np.int32)
        unique = 2
    else:
        # kmeans palette
        Z = rgb.reshape(-1, 3).astype(np.float32)
        K = int(np.clip(max_colors, 2, 8))
        _, labels, centers = cv2.kmeans(
            Z, K, None,
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.2),
            3,
            cv2.KMEANS_PP_CENTERS
        )
        palette = centers.astype(np.uint8)
        labels = labels.reshape(h, w).astype(np.int32)
        unique = K

    if layer_order.lower().startswith("dark"):
        order = np.argsort(
            (0.2126*palette[:,0] + 0.7152*palette[:,1] + 0.0722*palette[:,2])
        )  # darkest -> lightest
    else:
        order = np.argsort(
            (0.2126*palette[:,0] + 0.7152*palette[:,1] + 0.0722*palette[:,2])
        )[::-1]  # lightest -> darkest

    min_area = max(1, int(min_area_frac * h * w))

    paths: List[str] = []
    for idx in order:
        mask = (labels == int(idx)).astype(np.uint8) * 255

        if primitive_snap:
            kernel = np.ones((3,3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            if cv2.contourArea(c) < min_area:
                continue
            perim = max(1.0, cv2.arcLength(c, True))
            eps = 0.003 * perim  # tight
            approx = cv2.approxPolyDP(c, eps, True)
            if len(approx) < 3:
                continue
            d = " ".join(f"L {p[0][0]} {p[0][1]}" for p in approx[1:])
            d = f"M {approx[0][0][0]} {approx[0][0][1]} {d} Z"
            R, G, B = map(int, palette[idx])
            paths.append(
                f'<path d="{d}" fill="rgb({R},{G},{B})" stroke="none"/>'
            )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        + "".join(paths) +
        "</svg>"
    )
    return svg

# ---------- routes ----------

@app.get("/")
def root():
    return {"status": "ok", "service": "printready-vectorizer-api"}

@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    max_colors: int = Form(4),
    primitive_snap: bool = Form(False),
    min_path_area: float = Form(0.0002),
    layer_order: str = Form("Dark → Light"),
):
    data = await file.read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        return JSONResponse(status_code=400, content={"error": "bad_image"})

    if img.ndim == 3 and img.shape[2] == 4:
        # remove alpha by compositing against white
        alpha = img[..., 3:4] / 255.0
        base = np.full_like(img[..., :3], 255)
        img = (img[..., :3] * alpha + base * (1 - alpha)).astype(np.uint8)

    rgb = to_rgb(img)
    svg = vectorize_core(
        rgb,
        max_colors=max_colors,
        primitive_snap=primitive_snap,
        min_area_frac=float(min_path_area),
        layer_order=layer_order,
    )
    return {"svg": svg}
