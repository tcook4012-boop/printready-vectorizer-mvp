from .svg import paths_to_svg
from .preprocess import load_and_quantize
from .trace import extract_contours
from .simplify import simplify_paths
from .fit import fit_primitives_and_beziers
from .metrics import Metrics

def vectorize_image(img_bytes: bytes, max_colors:int=8, smoothness:str="medium",
                    primitive_snap:bool=True, hq_refine:bool=False, min_feature_px:int=4):
    # 1) Load + quantize (Lab + k-means)
    img_lab, palette, (w, h) = load_and_quantize(img_bytes, max_colors=max_colors)

    # 2) Extract contours per quantized color region
    raw_paths = extract_contours(img_lab, min_feature_px=min_feature_px)

    # 3) Simplify polylines (adaptive epsilon based on curvature & smoothness)
    simplified = simplify_paths(raw_paths, smoothness=smoothness)

    # 4) Primitive snapping + Bezier fitting
    beziers = fit_primitives_and_beziers(simplified, primitive_snap=primitive_snap)

    # (Optional) HQ refine placeholder — planned with distance-field energy
    # Skipped in MVP to keep runtime low and dependencies minimal.

    svg_bytes = paths_to_svg(beziers, width=w, height=h)
    node_count = sum(len(p['points']) for p in beziers)
    metrics = Metrics(node_count=node_count, path_count=len(beziers), width=w, height=h)
    return svg_bytes, metrics
