# backend/app/vectorizer/contours.py
import numpy as np
import cv2

def lightness_from_lab(img_lab: np.ndarray) -> np.ndarray:
    """Return uint8 lightness image (0..255) from LAB-like quantized image."""
    L = img_lab[..., 0].astype(np.float32)
    # NumPy 2.0: use np.ptp(L) instead of L.ptp()
    rng = float(np.ptp(L))  # max - min
    if rng < 1e-6:
        return np.zeros_like(L, dtype=np.uint8)
    L = (255.0 * (L - float(L.min())) / (rng + 1e-6)).astype(np.uint8)
    return L

def find_dark_region_contours(img_lab: np.ndarray, min_area_px: int = 6):
    """
    1) Take L channel, 2) Otsu threshold to get 'dark ink' mask, 3) find contours.
    Returns list of polygons with hole info.
    """
    L = lightness_from_lab(img_lab)

    # In these logos, dark ink = low L. Invert after Otsu to make ink=255.
    _, mask = cv2.threshold(L, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Close small gaps
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    # Find contours with hierarchy (handles holes)
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return []

    hier = hier[0]
    polys = []
    for i, c in enumerate(cnts):
        area = cv2.contourArea(c)
        if area < min_area_px:
            continue
        # simplify but keep corners; smaller epsilon preserves text edges
        epsilon = max(0.25, 0.01 * cv2.arcLength(c, True))
        approx = cv2.approxPolyDP(c, epsilon, True)
        pts = [(float(p[0][0]), float(p[0][1])) for p in approx]
        parent = hier[i][3]
        polys.append({"points": pts, "is_hole": parent != -1})
    return polys

def poly_to_cubics(pts):
    """Convert a polygon to a sequence of cubic Beziers (simple tangents)."""
    if len(pts) < 2:
        return []
    beziers = []
    n = len(pts)
    closed = (pts[0] == pts[-1])
    rng = range(n-1) if not closed else range(n)
    for i in rng:
        p0 = np.array(pts[i % n], dtype=np.float32)
        p3 = np.array(pts[(i+1) % n], dtype=np.float32)
        t = p3 - p0
        p1 = p0 + t / 3.0
        p2 = p0 + 2.0 * t / 3.0
        beziers.append([tuple(p0), tuple(p1), tuple(p2), tuple(p3)])
    return beziers
