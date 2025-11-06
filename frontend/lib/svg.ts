// frontend/lib/svg.ts
// Robust SVG normalizer:
// 1) Parse raw SVG.
// 2) Mount a copy in the DOM, call getBBox() to get true bounds.
// 3) Build a fresh root with viewBox="0 0 w h" and translate(-minX, -minY).
// 4) Responsive width/height and sane aspect ratio.
// This ensures the entire drawing is visible (no more “only a corner”).

export function normalizeSvg(raw: string) {
  // Parse twice: one copy for measuring, one for final output
  const parser = new DOMParser();
  const measureDoc = parser.parseFromString(raw, "image/svg+xml");
  const outputDoc = parser.parseFromString(raw, "image/svg+xml");

  const measureSvg = measureDoc.documentElement;
  const outputSvg = outputDoc.documentElement;

  if (measureSvg.tagName.toLowerCase() !== "svg") {
    throw new Error("normalizeSvg: not an <svg> root");
  }

  // Put the measuring SVG into the DOM so getBBox works
  const tempContainer = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  tempContainer.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  tempContainer.style.position = "absolute";
  tempContainer.style.left = "-99999px";
  tempContainer.style.top = "-99999px";
  tempContainer.style.width = "1px";
  tempContainer.style.height = "1px";
  tempContainer.style.visibility = "hidden";

  // Append the parsed SVG to the temp container
  // Use importNode to create real DOM nodes
  const measureNode = document.importNode(measureSvg, true);
  tempContainer.appendChild(measureNode);
  document.body.appendChild(tempContainer);

  // Compute true bounds
  let bbox = { x: 0, y: 0, w: 1000, h: 1000 };
  try {
    const b = (measureNode as unknown as SVGGraphicsElement).getBBox();
    bbox = { x: b.x, y: b.y, w: b.width || 1000, h: b.height || 1000 };
  } catch {
    // keep fallback
  }

  // Clean up measuring DOM
  document.body.removeChild(tempContainer);

  // Build a fresh root with 0-based viewBox
  const cleanRoot = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  cleanRoot.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  cleanRoot.setAttribute("viewBox", `0 0 ${bbox.w} ${bbox.h}`);
  cleanRoot.setAttribute("preserveAspectRatio", "xMidYMid meet");
  cleanRoot.setAttribute("width", "100%");
  cleanRoot.setAttribute("height", "100%");

  // Wrapper group to shift content into the 0-based viewBox
  const wrapper = document.createElementNS("http://www.w3.org/2000/svg", "g");
  // Translate content so minX/minY are at (0,0)
  wrapper.setAttribute("transform", `translate(${-bbox.x}, ${-bbox.y})`);

  // Move children from outputSvg into the wrapper (preserve original content)
  while (outputSvg.firstChild) {
    wrapper.appendChild(outputSvg.firstChild);
  }

  // Strip noisy attributes on the wrapper tree
  stripAttrsDeep(wrapper, ["shape-rendering", "image-rendering", "color-rendering", "transform-origin"]);

  cleanRoot.appendChild(wrapper);

  // Serialize
  const serializer = new XMLSerializer();
  return serializer.serializeToString(cleanRoot);
}

function stripAttrsDeep(el: Element, names: string[]) {
  names.forEach((n) => el.removeAttribute(n));
  Array.from(el.children).forEach((c) => stripAttrsDeep(c as Element, names));
}
