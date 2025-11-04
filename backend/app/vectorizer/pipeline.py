# backend/app/vectorizer/pipeline.py

from .svg import paths_to_svg
from .preprocess import load_and_quantize
from .contours import find_dark_region_contours, poly_to_cubics
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
    Load raster -> quantize (for stable L channel) -> find dark-region contours ->
    convert polygons to cubic Beziers -> return stroke-only SVG (sanity pass).
    """
    # 1) Load + quantize (for a stable LAB/L channel)
    img_lab, palette, (w, h) = load_and_quantize(img_bytes, max_colors=max_colors)

    # 2) Extract contours from dark regions (letters/shapes)
    polys = find_dark_region_contours(img_lab, min_area_px=max(min_feature_px, 6))

    # 3) Polygon rings -> cubic segments
    paths = []
    for poly in polys:
        cubics = poly_to_cubics(poly["points"])
        paths.append({"beziers": cubics, "is_hole": poly["is_hole"]})

    # 4) Stroke-only SVG for now (we'll switch to filled with colors next)
    svg_bytes = paths_to_svg(paths, width=w, height=h)

    node_count = sum(len(p["beziers"]) for p in paths)
    metrics = Metrics(node_count=node_count, path_count=len(paths), width=w, height=h)
    return svg_bytes, metrics
