// frontend/lib/svg.ts

/**
 * Normalize an SVG string so it can be safely injected into the page and scaled.
 * - Strips any namespace prefixes on tags/attrs (e.g., ns0:svg -> svg)
 * - Ensures there is a viewBox; if missing, synthesize from width/height or fallback
 * - Removes gigantic width/height so CSS can control sizing
 * - Wraps children in a group we can scale
 */
function stripNamespaces(svg: string): string {
  // Remove xmlns:* attributes but keep the base xmlns if present
  svg = svg.replace(/\s+xmlns:[a-zA-Z0-9_-]+="[^"]*"/g, "");

  // Replace namespaced tags like <ns0:svg> or </ns0:path> with <svg> / </path>
  svg = svg.replace(/<\/[a-zA-Z0-9_-]+:([a-zA-Z0-9_-]+)\s*>/g, "</$1>");
  svg = svg.replace(/<([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)(\s|>)/g, "<$2$3");

  // Also strip namespaced attributes like ns0:href -> href
  svg = svg.replace(/\s+[a-zA-Z0-9_-]+:([a-zA-Z0-9_-]+)=/g, " $1=");

  return svg;
}

function ensureViewBox(svg: string): string {
  // If there's already a viewBox, leave it
  if (/viewBox\s*=/.test(svg)) return svg;

  // Try to extract width/height (numbers only)
  const wMatch = svg.match(/width\s*=\s*"(\d+(\.\d+)?)"/i);
  const hMatch = svg.match(/height\s*=\s*"(\d+(\.\d+)?)"/i);

  const w = wMatch ? parseFloat(wMatch[1]) : 1024;
  const h = hMatch ? parseFloat(hMatch[1]) : 1024;

  // Inject a viewBox on the <svg ...> tag
  return svg.replace(
    /<svg\b([^>]*)>/i,
    (_m, attrs) => `<svg${attrs} viewBox="0 0 ${w} ${h}">`
  );
}

function dropExplicitSize(svg: string): string {
  // Remove width/height so CSS can control size in the preview
  svg = svg.replace(/\swidth\s*=\s*"[^"]*"/gi, "");
  svg = svg.replace(/\sheight\s*=\s*"[^"]*"/gi, "");
  return svg;
}

function wrapInViewportGroup(svg: string): string {
  // If it already has our wrapper, skip
  if (svg.includes('id="pr-viewport"')) return svg;

  // Put everything except the opening/closing <svg> into a <g> wrapper
  const openIdx = svg.indexOf(">");
  const closeIdx = svg.lastIndexOf("</svg>");
  if (openIdx === -1 || closeIdx === -1) return svg;

  const head = svg.slice(0, openIdx + 1);
  const body = svg.slice(openIdx + 1, closeIdx);
  const tail = svg.slice(closeIdx);

  return `${head}<g id="pr-viewport">${body}</g>${tail}`;
}

export function normalizeSvg(input: string): string {
  if (!input) return "";

  // Keep only the region between the first <svg and the last </svg>
  const start = input.toLowerCase().indexOf("<svg");
  const end = input.toLowerCase().lastIndexOf("</svg>");
  if (start === -1 || end === -1) return "";

  let svg = input.slice(start, end + "</svg>".length);

  svg = stripNamespaces(svg);
  svg = ensureViewBox(svg);
  svg = dropExplicitSize(svg);
  svg = wrapInViewportGroup(svg);

  // Guarantee an xmlns so browsers are happy
  if (!/xmlns=/.test(svg)) {
    svg = svg.replace(
      /<svg\b/,
      `<svg xmlns="http://www.w3.org/2000/svg"`
    );
  }

  return svg;
}
