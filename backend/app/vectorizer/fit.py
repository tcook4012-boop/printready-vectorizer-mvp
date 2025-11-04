import numpy as np

def fit_line(points):
    xs = np.array([p[0] for p in points])
    ys = np.array([p[1] for p in points])
    X = np.stack([xs, np.ones_like(xs)], axis=1)
    m, c = np.linalg.lstsq(X, ys, rcond=None)[0]
    y0 = m*xs[0]+c
    y1 = m*xs[-1]+c
    return [(xs[0], y0), (xs[-1], y1)]

def circle_fit_kasa(points):
    xs = np.array([p[0] for p in points])
    ys = np.array([p[1] for p in points])
    x = xs[:,None]; y = ys[:,None]
    A = np.hstack([2*x, 2*y, np.ones_like(x)])
    b = (xs**2 + ys**2)[:,None]
    c, *_ = np.linalg.lstsq(A, b, rcond=None)
    a, b_, d = c.flatten()
    cx, cy = a, b_
    r = np.sqrt(d + cx*cx + cy*cy)
    return (float(cx), float(cy), float(r))

def bezier_from_polyline(points):
    # MVP: each polyline segment becomes a cubic Bézier with control points along tangents
    if len(points) < 2:
        return []
    beziers = []
    for i in range(len(points)-1):
        p0 = np.array(points[i])
        p3 = np.array(points[i+1])
        t = p3 - p0
        p1 = p0 + t/3.0
        p2 = p0 + 2.0*t/3.0
        beziers.append([tuple(p0), tuple(p1), tuple(p2), tuple(p3)])
    return beziers

def fit_primitives_and_beziers(paths, primitive_snap=True):
    out = []
    for p in paths:
        pts = p["points"]
        if primitive_snap and len(pts) >= 4:
            # Snap nearly-collinear sequences to a straight line
            v0 = np.array(pts[-1]) - np.array(pts[0])
            if np.linalg.norm(v0) > 1e-6:
                # measure average distance to line
                x0,y0 = pts[0]
                vx,vy = v0/np.linalg.norm(v0)
                dists = []
                for x,y in pts:
                    d = abs((y - y0)*vx - (x - x0)*vy) # area formula approximation
                    dists.append(d)
                if np.mean(dists) < 0.5:  # threshold in pixels
                    line_pts = fit_line(pts)
                    beziers = bezier_from_polyline(line_pts)
                else:
                    beziers = bezier_from_polyline(pts)
            else:
                beziers = bezier_from_polyline(pts)
        else:
            beziers = bezier_from_polyline(pts)
        out.append({"points":pts, "beziers":beziers, "color":p.get("color",(1,0,0))})
    return out
