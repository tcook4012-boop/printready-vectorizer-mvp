# backend/app/vectorizer/pipeline.py
from .smart_vectorizer import SmartVectorizer
from .metrics import Metrics  # keep existing Metrics dataclass if you already have it

_vectorizer = None

def _get_vectorizer():
    global _vectorizer
    if _vectorizer is None:
        _vectorizer = SmartVectorizer()
    return _vectorizer

def vectorize_image(
    img_bytes: bytes,
    max_colors: int = 8,
    smoothness: str = "medium",
    primitive_snap: bool = True,  # currently unused; reserved for later snapping
    hq_refine: bool = False,      # reserved for future HQ mode
    min_feature_px: int = 4,      # reserved for future filtering
):
    """
    Returns: (svg_bytes, Metrics)
    """
    vec = _get_vectorizer()
    svg_bytes, metrics_dict = vec.vectorize(
        img_bytes,
        max_colors=max_colors,
        smoothness=smoothness
    )

    # Build Metrics (fallback estimate for node_count)
    metrics = Metrics(
        node_count=max(1, metrics_dict.get("layers", 0) * 40),
        path_count=metrics_dict.get("layers", 0),
        width=metrics_dict.get("width", 0),
        height=metrics_dict.get("height", 0),
    )
    return svg_bytes, metrics
