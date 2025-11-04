# backend/app/vectorizer/pipeline.py

import numpy as np
import cv2

from .svg import paths_to_svg
from .preprocess import load_and_quantize
from .contours import find_dark_region_contours, poly_to_cubics, lightness_from_lab
from .metrics import Metrics


def vectorize_image(
    img_bytes: bytes,
    max_colors: int = 8,
    smoothness: str = "medium",
    primitive_snap: bool = True,
    hq_refine: bool = False,
    min_feature_px: int = 4,
):
    """
    Load raster -> quantize -> contour dark/filled regions -> build filled color paths.
    """

    # 1) Load & quantize. Returns LAB-like image and (w, h)
    img_lab, palette, (w, h) = load_and_quantize(img_bytes, max_colors=max_colors)

    # 2) Get an 8-bit Lightness image for Otsu (fixes CV_32F error)
    L_u8 = lightness_from_lab(img_lab)  # guaranteed uint8 0..255

    # 3) Binary mask of "ink" (dark regions)
    _, mask = cv2.threshold(L_u8, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    # 4) Convert back to RGB (uint8) for color sampling
    # OpenCV expects 8-bit Lab for COLOR_Lab2RGB; ensure dtype is uint8
    img_lab_u8 = np.clip(img_lab, 0, 255).astype(np.uint8)
    img_rgb = cv2.cvtColor(img_lab_u8, cv2.COLOR_Lab2RGB)

    # 5) Extract polygons (with hole info) from dark regions
    polys = find_dark_region_contours(img_lab, min_area_px=max(min_feature_px, 6))

    # 6) Convert polygon rings to cubic Beziers and sample fill color
    paths = []
    for poly in polys:
        cubics = poly_to_cubics(poly["points"])

        # Sample average color from polygon region
        xys = np.array(poly["points"], dtype=np.int32)
        if xys.ndim == 2 and len(xys) > 2:
            poly_mask = np.zeros(mask.shape[:2], np.uint8)
            cv2.fillPoly(poly_mask, [xys], 255)
            mean_color = cv2.mean(img_rgb, mask=poly_mask)
            fill = f"rgb({int(mean_color[0])},{int(mean_color[1])},{int(mean_color[2])})"
        else:
            fill = "#000000"

        paths.append({"beziers": cubics, "is_hole": poly["is_hole"], "fill": fill})

    # 7) Output as FILLED SVG (holes handled with evenodd)
    svg_bytes = paths_to_svg(paths, width=w, height=h, filled=True)

    metrics = Metrics(
        node_count=sum(len(p["beziers"]) for p in paths),
        path_count=len(paths),
        width=w,
        height=h,
    )
    return svg_bytes, metrics
