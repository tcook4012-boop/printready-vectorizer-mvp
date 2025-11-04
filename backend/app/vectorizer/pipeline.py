# backend/app/vectorizer/pipeline.py

from .smart_vectorizer import SmartVectorizer
from .metrics import Metrics

# Initialize once (reused across requests)
_vectorizer = None

def get_vectorizer():
    global _vectorizer
    if _vectorizer is None:
        _vectorizer = SmartVectorizer()
    return _vectorizer

def vectorize_image(
    img_bytes: bytes,
    max_colors: int = 8,
    smoothness: str = "medium",
    primitive_snap: bool = True,
    hq_refine: bool = False,
    min_feature_px: int = 4,
):
    """
    High-quality vectorization using AI upscaling + smart tracing
    """
    
    vectorizer = get_vectorizer()
    
    # Run the smart vectorization pipeline
    svg_bytes, metrics_dict = vectorizer.vectorize(
        img_bytes, 
        max_colors=max_colors,
        smoothness=smoothness
    )
    
    # Build metrics object
    metrics = Metrics(
        node_count=metrics_dict.get("layers", 0) * 50,  # Estimate
        path_count=metrics_dict.get("layers", 0),
        width=metrics_dict.get("width", 0),
        height=metrics_dict.get("height", 0)
    )
    
    return svg_bytes, metrics
