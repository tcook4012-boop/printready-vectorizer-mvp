# backend/app/vectorizer/svg.py
from xml.etree.ElementTree import Element, SubElement, tostring

def _path_d_from_cubics(cubics):
    if not cubics:
        return ""
    # Start at first segment start, then add one 'C' per segment, then close 'Z'
    x0, y0 = cubics[0][0]
    parts = [f"M{x0:.2f},{y0:.2f}"]
    for (_, c1, c2, c3) in cubics:
        parts.append(
            f"C{c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {c3[0]:.2f},{c3[1]:.2f}"
        )
    parts.append("Z")
    return " ".join(parts)

def paths_to_svg(paths, width, height, filled=False):
    svg = Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        version="1.1",
        width=str(width),
        height=str(height),
        viewBox=f"0 0 {width} {height}",
    )
    for p in paths:
        d = _path_d_from_cubics(p["beziers"])
        el = SubElement(svg, "path", d=d)
        if filled:
            el.set("fill-rule", "evenodd")  # make holes cut properly
            el.set("fill", p.get("fill", "#000"))
            el.set("stroke", "none")
        else:
            el.set("fill", "none")
            el.set("stroke", "#000")
            el.set("stroke-width", "0.5")
    return tostring(svg, encoding="utf-8")
