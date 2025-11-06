import numpy as np
import cv2

def run_vectorizer(image_bgr, max_colors=2, min_area_frac=0.0002, smooth_level="low", invert_order=False):
    h, w = image_bgr.shape[:2]
    total_area = h * w
    min_area = total_area * min_area_frac

    # ---- STEP 1: Force binary style for high-contrast art ----
    # Convert to grayscale and threshold
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    thr, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Invert if needed (black letters / white background detection)
    if np.mean(binary) < 127:
        binary = cv2.bitwise_not(binary)

    # ---- STEP 2: Find all contours with hierarchy ----
    contours, hier = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # ---- STEP 3: Sort contours from big → small & ignore noise ----
    items = []
    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        if area < min_area: 
            continue
        parent = hier[0][i][3]
        items.append((area, cnt, parent))

    # Largest first
    items = sorted(items, key=lambda t: -t[0])

    # ---- STEP 4: Build SVG paths respecting child (holes) relationship ----
    svg_paths = []
    for _, cnt, parent in items:
        # Create a path string like M x,y L ...
        pts = cnt.reshape(-1, 2)
        d = f"M {pts[0][0]} {pts[0][1]} " + " ".join([f"L {p[0]} {p[1]}" for p in pts[1:]]) + " Z"

        if parent == -1:
            # Top-level contour → filled black
            svg_paths.append(f'<path d="{d}" fill="black" stroke="none" stroke-width="1"/>')
        else:
            # Child contour → subtract (white)
            svg_paths.append(f'<path d="{d}" fill="white" stroke="none" stroke-width="1"/>')

    # ---- STEP 5: Output SVG ----
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
    svg += "".join(svg_paths)
    svg += "</svg>"

    return svg
