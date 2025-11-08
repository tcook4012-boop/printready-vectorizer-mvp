import os
import io
import shutil
import subprocess
import tempfile
from typing import Optional, Tuple

import numpy as np
from PIL import Image
import cv2  # opencv-python-headless

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="PrintReady Vectorizer API")

# CORS: allow everything (tighten later if you want)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# --------- Utilities ------------
# -------------------------------

def _read_upload_to_cv2(upload: UploadFile) -> np.ndarray:
    """Read an UploadFile (JPG/PNG/etc.) into a BGR cv2 image."""
    data = upload.file.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # BGR, 8-bit
    if img is None:
        raise ValueError("Could not decode uploaded image")
    return img


def _save_temp_image(img_bgr: np.ndarray, suffix: str = ".png") -> str:
    """Write a cv2 BGR image to a temp PNG/JPG file and return path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    ok = cv2.imwrite(path, img_bgr)
    if not ok:
        raise ValueError("Failed to write temp image")
    return path


def _write_pgm_from_gray(gray: np.ndarray) -> str:
    """Save an 8-bit grayscale numpy array as PGM for Potrace and return path."""
    # Ensure uint8
    g = np.clip(gray, 0, 255).astype(np.uint8)
    fd, path = tempfile.mkstemp(suffix=".pgm")
    os.close(fd)
    # Use PIL to save PGM cleanly
    Image.fromarray(g).save(path, format="PPM")  # PPM/PGM uses same writer; mode "L" becomes PGM
    return path


def _lanczos_upscale_if_small(img_bgr: np.ndarray, target_min: int = 900, target_max: int = 1600) -> np.ndarray:
    """If the smaller side is below target_min, upscale with Lanczos to improve edges."""
    h, w = img_bgr.shape[:2]
    s = min(h, w)
    if s >= target_min:
        return img_bgr
    scale = min(target_max / max(h, w), target_min / s)
    if scale <= 1.0:
        return img_bgr
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    return cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)


def _denoise_jpeg(img_bgr: np.ndarray) -> np.ndarray:
    """Light edge-preserving denoise to remove JPEG blocks while keeping edges."""
    # Bilateral: diameter auto from size
    d = max(5, int(round(min(img_bgr.shape[:2]) * 0.01)))
    return cv2.bilateralFilter(img_bgr, d=d, sigmaColor=20, sigmaSpace=20)


def _detect_bg_mask_near_white(img_bgr: np.ndarray, tol: int = 18) -> np.ndarray:
    """
    Create a mask for near-white background to kill halos.
    Returns mask (uint8 0/255) where 255 = background.
    """
    img_lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(img_lab)
    # near-white → high L (brightness) and low chroma
    near_white = (L >= (255 - tol)).astype(np.uint8) * 255

    # expand slightly to catch fringes; then close gaps
    kernel = np.ones((3, 3), np.uint8)
    near_white = cv2.morphologyEx(near_white, cv2.MORPH_CLOSE, kernel, iterations=1)
    near_white = cv2.morphologyEx(near_white, cv2.MORPH_OPEN, kernel, iterations=1)
    return near_white


def _apply_white_bg_cleanup(img_bgr: np.ndarray) -> np.ndarray:
    """Replace near-white fringe with pure white to avoid colored halos."""
    mask = _detect_bg_mask_near_white(img_bgr, tol=20)
    # Where mask==255, set to pure white
    white = np.full_like(img_bgr, 255, dtype=np.uint8)
    cleaned = np.where(mask[..., None] == 255, white, img_bgr)
    return cleaned


def _auto_k_colors(img_bgr: np.ndarray, k_min: int = 2, k_max: int = 6) -> int:
    """
    Estimate a good number of colors for logos (keeps it small).
    Simple elbow on KMeans inertia, returns in [k_min, k_max].
    """
    # Sample down for speed
    small = cv2.resize(img_bgr, (0, 0), fx=0.33, fy=0.33, interpolation=cv2.INTER_AREA)
    data = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)

    from sklearn.cluster import KMeans
    inertias = []
    Ks = list(range(k_min, k_max + 1))
    for k in Ks:
        km = KMeans(n_clusters=k, n_init="auto", random_state=0).fit(data)
        inertias.append(km.inertia_)

    # elbow: pick k where drop ratio flattens
    drops = [inertias[i] - inertias[i + 1] for i in range(len(inertias) - 1)]
    if not drops:
        return max(k_min, min(4, k_max))
    # first k where drop is < 15% of first drop
    first = max(drops[0], 1e-6)
    for i, d in enumerate(drops):
        if d < 0.15 * first:
            return Ks[i + 1]
    return Ks[min(2, len(Ks) - 1)]  # fallback ~3–4


def _quantize_lab(img_bgr: np.ndarray, k: int) -> np.ndarray:
    """
    KMeans quantization in Lab space for clean, flat palette.
    """
    img_lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    h, w = img_lab.shape[:2]
    data = img_lab.reshape(-1, 3).astype(np.float32)

    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=k, n_init="auto", random_state=0).fit(data)
    centers = km.cluster_centers_.astype(np.float32)
    labels = km.labels_
    quant = centers[labels].reshape(h, w, 3)

    out_bgr = cv2.cvtColor(quant.astype(np.uint8), cv2.COLOR_LAB2BGR)

    # small morphological open/close to remove 1–2 px specks
    kernel = np.ones((3, 3), np.uint8)
    out_bgr = cv2.morphologyEx(out_bgr, cv2.MORPH_OPEN, kernel, iterations=1)
    out_bgr = cv2.morphologyEx(out_bgr, cv2.MORPH_CLOSE, kernel, iterations=1)
    return out_bgr


def _run_cmd(cmd: list) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _vectorize_vtracer(inp_path: str, out_path: str, *, max_colors: int, corner_threshold: float, filter_speckle: int, smoothing: str) -> Tuple[int, str, str, list]:
    mode = "spline" if smoothing in ("smooth", "spline") else "polygon"
    cmd = [
        "vtracer",
        "--input", inp_path,
        "--output", out_path,
        "--mode", mode,
        "--color_precision", str(max_colors),
        "--corner_threshold", str(int(corner_threshold)),
        "--filter_speckle", str(int(filter_speckle)),
    ]
    code, out, err = _run_cmd(cmd)
    return code, out, err, cmd


def _vectorize_potrace(inp_pgm: str, out_path: str) -> Tuple[int, str, str, list]:
    cmd = ["potrace", inp_pgm, "-s", "-o", out_path, "--longcoding"]
    code, out, err = _run_cmd(cmd)
    return code, out, err, cmd


# -------------------------------
# ----------- API ---------------
# -------------------------------

@app.post("/vectorize", response_class=PlainTextResponse)
async def vectorize(
    file: UploadFile = File(...),

    # User-visible knobs (can be ignored—pipeline picks good defaults)
    max_colors: Optional[int] = Form(None),             # if None → auto
    smoothing: str = Form("precision"),                 # "precision" or "smooth"
    corner_threshold: str = Form("60"),                 # stronger corners clean halos
    filter_speckle: str = Form("12"),
    engine: str = Form("auto"),                         # "auto" | "vtracer" | "potrace"
):
    tmp_paths = []
    try:
        # 1) Load
        img = _read_upload_to_cv2(file)

        # 2) Auto-upscale small inputs: better edge placement
        img = _lanczos_upscale_if_small(img, target_min=900, target_max=1600)

        # 3) Light denoise to reduce JPEG blockiness
        img = _denoise_jpeg(img)

        # 4) Kill white/pink halos (replace near-white with pure white)
        img = _apply_white_bg_cleanup(img)

        # 5) Decide color count if not provided
        k = int(max_colors) if max_colors is not None else _auto_k_colors(img, 2, 6)
        k = max(2, min(8, k))

        # 6) Palette quantization → flat colors, crisp edges
        img_q = _quantize_lab(img, k)

        # 7) Engine choice
        chosen_engine = engine
        if engine == "auto":
            chosen_engine = "potrace" if k <= 2 else "vtracer"

        # 8) Write intermediate input for tracer
        if chosen_engine == "potrace":
            # Potrace needs binary/grayscale PGM with a threshold
            gray = cv2.cvtColor(img_q, cv2.COLOR_BGR2GRAY)
            # Otsu to get a clean binary; invert if background is black-ish
            _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            inp_pgm = _write_pgm_from_gray(th)
            tmp_paths.append(inp_pgm)

            out_svg = tempfile.mktemp(suffix=".svg")
            code, out, err, cmd = _vectorize_potrace(inp_pgm, out_svg)
            if code != 0 or (not os.path.exists(out_svg)) or os.path.getsize(out_svg) == 0:
                return JSONResponse(status_code=500, content={"error": "vectorization failed", "stdout": out, "stderr": err, "cmd": cmd})

        else:
            # VTracer path (multi-color)
            inp_png = _save_temp_image(img_q, suffix=".png")
            tmp_paths.append(inp_png)

            out_svg = tempfile.mktemp(suffix=".svg")
            code, out, err, cmd = _vectorize_vtracer(
                inp_png, out_svg,
                max_colors=k,
                corner_threshold=float(corner_threshold or 60),
                filter_speckle=int(filter_speckle or 12),
                smoothing=smoothing,
            )
            if code != 0 or (not os.path.exists(out_svg)) or os.path.getsize(out_svg) == 0:
                return JSONResponse(status_code=500, content={"error": "vectorization failed", "stdout": out, "stderr": err, "cmd": cmd})

        # 9) Return raw SVG
        with open(out_svg, "r", encoding="utf-8", errors="ignore") as f:
            svg = f.read()
        return PlainTextResponse(svg, media_type="image/svg+xml")

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    finally:
        # cleanup
        for p in tmp_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except:
                pass
        # out_svg is named in engine blocks; best-effort removal
        try:
            if "out_svg" in locals() and os.path.exists(out_svg):
                os.remove(out_svg)
        except:
            pass
