# backend/app/vectorizer/svg.py
from io import BytesIO
from xml.etree.ElementTree import Element, SubElement, tostring

def paths_to_svg(paths, width, height, filled=False):
    """Convert vector paths (cubic lists) to SVG XML."""
    svg = Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        version="1.1",
        width=str(width),
        height=str(height),
        viewBox=f"0 0 {width} {height}",
    )
    for p in paths:
        d = []
        for b in p["beziers"]:
            x0, y0 = b[0]
            d.append(f"M{x0:.2f},{y0:.2f}")
            for _, c1, c2, c3 in [b]:
                d.append(f"C{c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {c3[0]:.2f},{c3[1]:.2f}")
        path = SubElement(svg, "path", d=" ".join(d))
        if filled:
            path.set("fill-rule", "evenodd")
            path.set("fill", p.get("fill", "#000"))
            path.set("stroke", "none")
        else:
            path.set("fill", "none")
            path.set("stroke", "#000")
            path.set("stroke-width", "0.5")
    return tostring(svg, encoding="utf-8")
