# backend/app/vectorizer/svg.py
from xml.sax.saxutils import escape

def path_from_cubics(cubics):
    d = []
    first = True
    start = None
    for b in cubics:
        (x0,y0),(x1,y1),(x2,y2),(x3,y3) = b
        if first:
            d.append(f"M {x0:.2f} {y0:.2f}")
            start = (x0, y0)
            first = False
        d.append(f"C {x1:.2f} {y1:.2f}, {x2:.2f} {y2:.2f}, {x3:.2f} {y3:.2f}")
    if start is not None:
        d.append("Z")
    return " ".join(d)

def paths_to_svg(bezier_paths, width:int, height:int)->bytes:
    header = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
    body = []
    # Stroke-only so we don't fill everything black while we validate contours.
    # Using evenodd anyway (will matter when we switch back to filled paths).
    for p in bezier_paths:
        d = path_from_cubics(p["beziers"])
        body.append(f'<path d="{escape(d)}" fill="none" stroke="black" stroke-width="1" fill-rule="evenodd" />')
    footer = "</svg>"
    return (header + "".join(body) + footer).encode("utf-8")
