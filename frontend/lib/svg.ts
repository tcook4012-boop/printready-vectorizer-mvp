// frontend/lib/svg.ts
// Fits any incoming <svg> to its true bounding box so nothing is clipped.
// Strategy:
//  - Keep existing viewBox if present (assume backend set it correctly).
//  - Otherwise, measure the geometry in a hidden <svg> in the DOM (getBBox())
//    and set viewBox="minX minY width height".
//  - Make the SVG responsive (width/height 100%, preserveAspectRatio meet).
//  - Strip noisy attrs; don't invent transforms.

export function normalizeSvg(raw: string) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(raw, "image/svg+xml");

  const svg = doc.documentElement;
  if (svg.tagName.toLowerCase() !== "svg") {
    throw new Error("normalizeSvg: not an <svg> root");
  }

  // Always make responsive
  svg.removeAttribute("width");
  svg.removeAttribute("height");
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", "100%");
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

  // If a viewBox already exists, keep it (assume backend was correct)
  const alreadyHasVB = !!svg.getAttribute("viewBox");

  // Remove suspicious transforms on the root and direct <g>
  svg.removeAttribute("transform");
  Array.from(svg.children).forEach((child) => {
    if (child.nodeName.toLowerCase() === "g") {
      (child as Element).removeAttribute("transform");
    }
  });

  // Strip rarely helpful rendering hints that sometimes break previews
  stripAttrsDeep(svg, ["shape-rendering", "image-rendering", "color-rendering"]);

  if (!alreadyHasVB) {
    // We need to measure the true bounds in the browser.
    // Create a temporary measuring container off-screen.
    const temp = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    temp.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    temp.style.position = "absolute";
    temp.style.visibility = "hidden";
    temp.style.pointerEvents = "none";
    temp.style.width = "0";
    temp.style.height = "0";

    // Import the nodes from the parsed doc into the live DOM <svg>
    // We clone the root's children into the temp container for measurement.
    while (svg.attributes.length > 0) svg.removeAttribute(svg.attributes[0].name);
    const originalChildren = Array.from(doc.documentElement.childNodes);
    const liveGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    originalChildren.forEach((n) => {
      const imported = document.importNode(n, true);
      liveGroup.appendChild(imported);
    });
    temp.appendChild(liveGroup);
    document.body.appendChild(temp);

    // Measure
    let bbox;
    try {
      // getBBox works only when in the live DOM
      const b = (liveGroup as unknown as SVGGraphicsElement).getBBox();
      bbox = { x: b.x, y: b.y, w: b.width, h: b.height };
    } catch {
      // Last-resort fallback if measurement fails
      bbox = { x: 0, y: 0, w: 1000, h: 1000 };
    }

    // Build a fresh root <svg> with correct viewBox and responsive size
    const newRoot = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    newRoot.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    newRoot.setAttribute("viewBox", `${bbox.x} ${bbox.y} ${bbox.w} ${bbox.h}`);
    newRoot.setAttribute("preserveAspectRatio", "xMidYMid meet");
    newRoot.setAttribute("width", "100%");
    newRoot.setAttribute("height", "100%");

    // Move measured content into the new root
    newRoot.appendChild(liveGroup);

    // Serialize and clean up
    const serializer = new XMLSerializer();
    const out = serializer.serializeToString(newRoot);
    document.body.removeChild(temp);
    return out;
  }

  // Serialize when original viewBox already existed
  const serializer = new XMLSerializer();
  return serializer.serializeToString(svg);
}

function stripAttrsDeep(el: Element, names: string[]) {
  names.forEach((n) => el.removeAttribute(n));
  Array.from(el.children).forEach((c) => stripAttrsDeep(c as Element, names));
}
