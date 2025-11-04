# backend/app/vectorizer/pipeline.py
from .svg import paths_to_svg
from .preprocess import load_and_quantize
from .contours import find_filled_contours, poly_to_cubics
from .metrics import Metrics

def vectorize_image(img_bytes: bytes, max_colors:int=8, smoothness:str="medium",
                    primitive_snap:bool=True, hq_refine:bool=False, min_feature_px:int=4):
    # 1) Load + quantize
    img_lab, palette, (w, h) = load_and_quantize(img_bytes, max_colors=max_colors)

    # 2) Extract filled contours per color region
    polys = find_filled_contours(img_lab, min_area_px=max(min_feature_px, 12))

    # 3) Convert polygons to cubic Beziers
    beziers = []
    for poly in polys:
        cubics = poly_to_cubics(poly["points"])
        beziers.append({"beziers": cubics, "is_hole": poly["is_hole"]})

    # 4) Render as filled paths (holes handled by path direction later)
    svg_bytes = paths_to_svg(beziers, width=w, height=h)
    node_count = sum(len(b["beziers"]) for b in beziers)
    metrics = Metrics(node_count=node_count, path_count=len(beziers), width=w, height=h)
    return svg_bytes, metrics
