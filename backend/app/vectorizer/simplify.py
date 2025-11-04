import numpy as np
from math import hypot

def rdp(points, epsilon):
    # Ramer–Douglas–Peucker for polyline
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]

    def perp_dist(p, a, b):
        ax, ay = a; bx, by = b; px, py = p
        dx, dy = bx-ax, by-ay
        if dx==dy==0:
            return hypot(px-ax, py-ay)
        t = ((px-ax)*dx + (py-ay)*dy) / (dx*dx + dy*dy)
        t = max(0, min(1, t))
        cx, cy = (ax + t*dx, ay + t*dy)
        return hypot(px-cx, py-cy)

    max_d, idx = 0.0, 0
    for i in range(1, len(points)-1):
        d = perp_dist(points[i], start, end)
        if d > max_d:
            idx, max_d = i, d
    if max_d > epsilon:
        left = rdp(points[:idx+1], epsilon)
        right = rdp(points[idx:], epsilon)
        return left[:-1] + right
    else:
        return [start, end]

def simplify_paths(paths, smoothness="medium"):
    eps = {"low": 0.5, "medium": 1.0, "high": 2.0}.get(smoothness, 1.0)
    out = []
    for p in paths:
        pts = [(float(x), float(y)) for x,y in p["points"]]
        simp = rdp(pts, eps)
        out.append({"points":simp, "color":p.get("color",(1,0,0))})
    return out
