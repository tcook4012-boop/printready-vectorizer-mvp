# backend/app/vectorizer/smart_vectorizer.py
import os
import re
import tempfile
import subprocess
from typing import Dict, List, Tuple

import cv2
import numpy as np

from .preprocess import preprocess_image

def _bgr_to_hex(color_bgr: np.ndarray) -> str:
    b, g, r = [int(x) for x in color_bgr]
    return f"#{r:02x}{g:02x}{b:02x}"

def _unique_colors(img_bgr: np.ndarray, max_colors: int) -> np.ndarray:
    """
    After LAB quantization we still may have tiny shade variations.
    We reduce to at most max_colors by picking the top-N most frequent colors.
    """
    flat = img_bgr.reshape(-1, 3)
    # counts per unique row
    uniques, counts = np.unique(flat, axis=0, return_counts=True)
    # sort by frequency desc
    order = np.argsort(-counts)
    uniques = uniques[order]
    if len(uniques) > max_colors:
        uniques = uniques[:max_colors]
    return uniques

def _color_mask(img_bgr: np.ndarray, target_bgr: np.ndarray, tol: int = 2) -> np.ndarray:
    """
    Create a binary mask for pixels near target color within tolerance.
    """
    lower = np.clip(target_bgr - tol, 0, 255).astype(np.uint8)
    upper = np.clip(target_bgr + tol, 0, 255).astype(np.uint8)
    mask = cv2.inRange(img_bgr, lower, upper)
    # cleanup small speckles / holes
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return mask

def _trace_with_potrace(mask: np.ndarray, alphamax: float, opttolerance: float) -> List[str]:
    """
    Send a binary mask to Potrace and return a list of SVG path 'd' strings.
    We parse all paths from the generated SVG.
    """
    paths: List[str] = []
    with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as f_bmp:
        bmp_path = f_bmp.name
        # Potrace expects 1-channel BMP with 0/255
        cv2.imwrite(bmp_path, mask)

    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f_svg:
        svg_path = f_svg.name

    try:
        cmd = [
            "potrace",
            bmp_path,
            "-s",
            "-o", svg_path,
            "--turdsize", "2",
            "--alphamax", str(alphamax),
            "--opttolerance", str(opttolerance),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Potrace error; return empty
            return []

        with open(svg_path, "r", encoding="utf-8", errors="ignore") as fh:
            svg_text = fh.read()

        # extract every path d="..."
        for m in re.finditer(r'd="([^"]+)"', svg_text):
            paths.append(m.group(1))
    finally:
        try:
            os.remove(bmp_path)
        except Exception:
            pass
        try:
            os.remove(svg_path)
        except Exception:
            pass

    return paths

class SmartVectorizer:
    """
    Lightweight, deployable vectorizer:
      - OpenCV denoise + LAB quantization
      - Per-color masks
      - Potrace tracing
    No PyTorch / ESRGAN dependencies.
    """

    def __init__(self):
        # Default smoothing parameters (balanced)
        self.alphamax = 1.0       # corner v. curve
        self.opttolerance = 0.2   # curve optimization

    def vectorize(self, image_bytes: bytes, max_colors: int = 8, smoothness: str = "medium") -> Tuple[bytes, Dict]:
        # Preprocess & get original size for viewBox
        quant_bgr, (orig_w, orig_h) = preprocess_image(image_bytes, max_colors=max_colors)

        # Adjust smoothing based on requested smoothness
        if smoothness == "low":
            alphamax, opttol = 0.5, 0.1
        elif smoothness == "high":
            alphamax, opttol = 1.5, 0.4
        else:
            alphamax, opttol = self.alphamax, self.opttolerance

        # Determine the representative colors to iterate (cap at max_colors)
        colors = _unique_colors(quant_bgr, max_colors=max_colors)

        svg_elements: List[str] = []
        layer_count = 0

        # Trace each color into one or more paths
        for color_bgr in colors:
            mask = _color_mask(quant_bgr, color_bgr, tol=2)
            if cv2.countNonZero(mask) < 10:
                continue

            # Potrace returns list of path 'd' strings
            d_list = _trace_with_potrace(mask, alphamax, opttol)
            if not d_list:
                continue

            fill_hex = _bgr_to_hex(color_bgr)
            for d in d_list:
                svg_elements.append(
                    f'<path d="{d}" fill="{fill_hex}" stroke="none" fill-rule="evenodd"/>'
                )
                layer_count += 1

        # Compose final SVG with original viewBox
        svg = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{orig_w}" height="{orig_h}" viewBox="0 0 {orig_w} {orig_h}">'
        ]
        svg.extend(svg_elements)
        svg.append("</svg>")
        svg_bytes = ("\n".join(svg)).encode("utf-8")

        metrics = {
            "width": orig_w,
            "height": orig_h,
            "layers": layer_count,
            "colors": int(min(max_colors, len(colors)))
        }
        return svg_bytes, metrics
