# backend/app/vectorizer/pipeline.py
from .svg import paths_to_svg
from .preprocess import load_and_quantize
from .contours import find_dark_region_contours, poly_to_cubics
from .metrics import Metrics
import numpy as np
import cv2

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
    img_lab, palette, (w, h) = load_and_quantize(img_bytes, max_colors=max_colors)
    L = img_lab[..., 0]

    # Convert back to RGB for color sampling
    img_rgb = cv2.cvtColor(img_lab, cv2.COLOR_Lab2RGB)

    # Build a binary mask (dark = ink)
    _, mask = cv2.threshold(L, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    polys = find_dark_region_contours(img_lab, min_area_px=max(min_feature_px, 6))

    paths = []
    for poly in polys:
        cubics = poly_to_cubics(poly["points"])
        # Sample average color from the area
        xys = np.array(poly["points"], dtype=np.int32)
        if xys.ndim == 2 and len(xys) > 2:
            mask_poly = np.zeros(mask.shape[:2], np.uint8)
            cv2.fillPoly(mask_poly, [xys], 255)
            mean_color = cv2.mean(img_rgb, mask=mask_poly)
            fill = f"rgb({int(mean_color[0])},{int(mean_color[1])},{int(mean_color[2])})"
        else:
            fill = "#000000"
        paths.append({"beziers": cubics, "is_hole": poly["is_hole"], "fill": fill})

    svg_bytes = paths_to_svg(paths, width=w, height=h, filled=True)

    metrics = Metrics(
        node_count=sum(len(p["beziers"]) for p in paths),
        path_count=len(paths),
        width=w,
        height=h,
    )
    return svg_bytes, metrics
