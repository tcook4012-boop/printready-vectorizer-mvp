// frontend/lib/svg.ts
export function normalizeSvg(raw: string) {
  // Parse XML
  const parser = new DOMParser();
  const doc = parser.parseFromString(raw, "image/svg+xml");
  const svg = doc.documentElement;

  // Ensure valid root tag
  if (svg.tagName.toLowerCase() !== "svg") {
    throw new Error("normalizeSvg: not an <svg> root");
  }

  // Remove width/height (use viewBox + 100%)
  svg.removeAttribute("width");
  svg.removeAttribute("height");

  // Ensure viewBox
  const vb = svg.getAttribute("viewBox");
  if (!vb) {
    // Try to infer from paths’ bounding box; fallback to 0..1000 if unknown
    const bbox = computeBBox(doc);
    svg.setAttribute("viewBox", `${bbox.x} ${bbox.y} ${bbox.w} ${bbox.h}`);
  }

  // Enforce responsive sizing + sane aspect ratio handling
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", "100%");

  // Remove suspicious global transforms on <svg> or top-level <g>
  svg.removeAttribute("transform");
  const rootGs = Array.from(svg.children).filter(n => n.nodeName === "g");
  rootGs.forEach((g: Element) => {
    if (g.hasAttribute("transform")) {
      // Don’t attempt to mathematically bake transforms (slow on client).
      // Instead, wrap into a group-neutral state by moving transform down to children if safe,
      // or drop it if it’s a pure translate/scale that breaks framing.
      const t = g.getAttribute("transform") || "";
      if (/^translate\(\s*0[, ]\s*0\s*\)\s*$/.test(t)) {
        g.removeAttribute("transform");
      }
      // If it's a giant scale that causes black fills across canvas, drop it.
      if (/scale\(\s*(?:-?\d+(\.\d+)?e?\-?\d*)\s*(?:[, ]\s*(-?\d+(\.\d+)?e?\-?\d*))?\s*\)/i.test(t)) {
        g.removeAttribute("transform");
      }
    }
  });

  // Sort layers by fill luminance to improve stacking (optional but helps)
  sortPathsByLuminance(svg);

  // Strip obviously invalid attributes that sometimes appear
  stripNoisyAttrs(svg, ["shape-rendering", "image-rendering", "color-rendering"]);

  const serializer = new XMLSerializer();
  return serializer.serializeToString(svg);
}

function computeBBox(doc: Document) {
  // Heuristic bbox; if paths lack bbox we fall back to 0..1000
  const paths = Array.from(doc.getElementsByTagName("path"));
  const rects = Array.from(doc.getElementsByTagName("rect"));
  const circles = Array.from(doc.getElementsByTagName("circle"));
  const ellipses = Array.from(doc.getElementsByTagName("ellipse"));
  const polys = Array.from(doc.getElementsByTagName("polygon"));
  const lines = Array.from(doc.getElementsByTagName("line"));

  // If no geometry, fallback
  if (
    paths.length + rects.length + circles.length + ellipses.length + polys.length + lines.length === 0
  ) {
    return { x: 0, y: 0, w: 1000, h: 1000 };
  }
  // Without computing true path bbox (expensive), give a stable viewBox
  // that won’t clip: 0..1000. Backends should set an accurate viewBox later.
  return { x: 0, y: 0, w: 1000, h: 1000 };
}

function stripNoisyAttrs(el: Element, names: string[]) {
  names.forEach(n => el.removeAttribute(n));
  Array.from(el.children).forEach(c => stripNoisyAttrs(c as Element, names));
}

function sortPathsByLuminance(svg: Element) {
  const nodes = Array.from(svg.querySelectorAll("path,polygon,polyline,rect,circle,ellipse"));
  const entries = nodes.map(n => {
    const fill = (n.getAttribute("fill") || "#000").trim();
    const lum = hexOrRgbToLum(fill);
    return { n, lum };
  });
  // Light-to-dark (or flip if your outputs look better reversed)
  entries.sort((a, b) => a.lum - b.lum);
  // Re-append in order
  entries.forEach(e => e.n.parentElement?.appendChild(e.n));
}

function hexOrRgbToLum(c: string) {
  // Accepts #rgb/#rrggbb or rgb(a)
  let r = 0, g = 0, b = 0;
  if (c.startsWith("#")) {
    const hex = c.slice(1);
    if (hex.length === 3) {
      r = parseInt(hex[0] + hex[0], 16);
      g = parseInt(hex[1] + hex[1], 16);
      b = parseInt(hex[2] + hex[2], 16);
    } else if (hex.length >= 6) {
      r = parseInt(hex.slice(0, 2), 16);
      g = parseInt(hex.slice(2, 4), 16);
      b = parseInt(hex.slice(4, 6), 16);
    }
  } else if (c.startsWith("rgb")) {
    const m = c.match(/rgb[a]?\(([^)]+)\)/i);
    if (m) {
      const parts = m[1].split(",").map(s => parseFloat(s));
      [r, g, b] = parts;
    }
  }
  // sRGB luminance
  const [R, G, B] = [r, g, b].map(v => {
    const x = v / 255;
    return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * R + 0.7152 * G + 0.0722 * B;
}
