# backend/app/vectorizer/preprocess.py
import io
from typing import Tuple
import numpy as np
import cv2

def _denoise(img_bgr: np.ndarray) -> np.ndarray:
    # Gentle denoise that preserves edges
    # 1) Bilateral to remove jpeg artifacts
    img = cv2.bilateralFilter(img_bgr, d=9, sigmaColor=75, sigmaSpace=75)
    # 2) Very light median to knock single-pixel noise
    img = cv2.medianBlur(img, 3)
    return img

def _maybe_upscale(img_bgr: np.ndarray, min_side: int = 800) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    s = min(h, w)
    if s >= min_side:
        return img_bgr
    scale = float(min_side) / float(s)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    return cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

def _quantize_lab(img_bgr: np.ndarray, n_colors: int) -> np.ndarray:
    """
    Perceptual (LAB) k-means quantization.
    Ensures clean, consistent color regions for better tracing.
    """
    img_lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    pixels = img_lab.reshape(-1, 3).astype(np.float32)

    # k-means
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 80, 0.25)
    # cap colors to [2..16] sane range
    k = int(max(2, min(16, n_colors)))
    _, labels, palette = cv2.kmeans(
        data=pixels,
        K=k,
        bestLabels=None,
        criteria=criteria,
        attempts=8,
        flags=cv2.KMEANS_PP_CENTERS
    )
    quant_lab = palette[labels.flatten()].reshape(img_lab.shape).astype(np.uint8)
    quant_bgr = cv2.cvtColor(quant_lab, cv2.COLOR_LAB2BGR)
    return quant_bgr

def _morphology_cleanup(mask: np.ndarray) -> np.ndarray:
    """
    Clean binary mask: remove dust and fill tiny holes.
    """
    # Ensure binary (0/255)
    if mask.dtype != np.uint8:
        mask = mask.astype(np.uint8)
    # Open (remove small white noise)
    kernel = np.ones((3, 3), np.uint8)
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    # Close (fill tiny holes)
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel, iterations=1)
    return closed

def preprocess_image(image_bytes: bytes, max_colors: int) -> Tuple[np.ndarray, Tuple[int, int]]:
    """
    Load -> optional upscale -> denoise -> LAB quantize.
    Returns:
        quant_bgr (np.ndarray): preprocessed BGR image ready for color-layer tracing
        original_size (w, h): original input size for viewBox generation
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode input image")

    h, w = img.shape[:2]
    original_size = (w, h)

    img = _maybe_upscale(img, min_side=800)
    img = _denoise(img)
    img = _quantize_lab(img, n_colors=max_colors)

    return img, original_size
