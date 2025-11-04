import cv2
import numpy as np
from .preprocess import preprocess_image
from .contours import extract_color_contours
from .svg import paths_to_svg

class SmartVectorizer:
    def __init__(self):
        pass  # no models needed

    def vectorize(self, img_bytes, max_colors=8, smoothness="medium", primitive_snap=True, min_feature_px=4):
        # Preprocess (denoise + color quantization + morphology)
        img_lab, color_map = preprocess_image(img_bytes, max_colors=max_colors)

        # Find shape regions per color
        polys = extract_color_contours(
            img_lab,
            min_area_px=max(min_feature_px, 4),
            smoothness=smoothness
        )

        # Convert to SVG
        svg_bytes = paths_to_svg(polys, color_map, snap_nodes=primitive_snap)

        metrics = {
            "colors_used": len(color_map),
            "shapes": len(polys)
        }

        return svg_bytes, metrics
