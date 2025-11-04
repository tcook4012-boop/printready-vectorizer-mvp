# backend/app/vectorizer/contours.py
import numpy as np
import cv2

def to_gray_labL(img_lab: np.ndarray) -> np.ndarray:
    # Use L channel (lightness) from LAB-like array we produced
    L = img_lab[..., 0].astype(np.float32)
    L = np.clip(L, 0, None)
    L = (255.0 * (L - L.min()) / (L.ptp() + 1e-6)).astype(np.uint8)
    return L

def find_filled_contours(img_lab: np.ndarray, min_area_px: int = 12):
    """
    Returns a list of filled polygons (each as list of (x,y) floats) from a quantized LAB image.
    We binarize per unique color region to get proper filled shapes.
    """
    H, W, _ = img_lab.shape
    # k-means outputs continuous palette; round to small bins so we can mask per-region
    rounded = np.round(img_lab / 2.0).astype(np.int16)  # coarse bucketize
    # encode LAB triplet to single int key
    keys = (rounded[..., 0] << 16) + (rounded[..., 1] << 8) + (rounded[..., 2])
    uniq = np.unique(keys)
    all_polys = []

    for key in uniq:
        mask = (keys == key).astype(np.uint8) * 255
        if mask.sum() < min_area_px:
            continue
        # close tiny gaps
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8))
        # contour extraction with hierarchy (handles holes)
        cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hier is None:
            continue
        hier = hier[0]
        for i, c in enumerate(cnts):
            area = cv2.contourArea(c)
            if area < min_area_px:
                continue
            # simplify polygon while preserving corners
            epsilon = 0.75  # px; will be parameterized later
            approx = cv2.approxPolyDP(c, epsilon, True)
            pts = [(float(p[0][0]), float(p[0][1])) for p in approx]
            # Determine if hole or outer by hierarchy parent
            parent = hier[i][3]
            all_polys.append({"points": pts, "is_hole": parent != -1})
    return all_polys

def poly_to_cubics(pts):
    """
    Convert polyline to a list of cubic Beziers by assigning simple tangents.
    (We’ll upgrade to curvature-aware later.)
    """
    if len(pts) < 2:
        return []
    beziers = []
    n = len(pts)
    closed = (pts[0] == pts[-1])
    rng = range(n-1) if not closed else range(n)
    for i in rng:
        p0 = np.array(pts[i % n])
        p3 = np.array(pts[(i+1) % n])
        t = p3 - p0
        p1 = p0 + t/3.0
        p2 = p0 + 2.0*t/3.0
        beziers.append([tuple(p0), tuple(p1), tuple(p2), tuple(p3)])
    return beziers
