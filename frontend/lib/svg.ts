// ✅ NEW svg.ts (drop-in replacement)
// Accepts raw SVG text — returns clean SVG string
// Handles DOCTYPE, XML header, comments, whitespace, etc.

export function normalizeSvg(raw: string): string {
  if (!raw) return "";

  let svg = raw.trim();

  // Remove XML header or DOCTYPE — browser doesn’t need it
  svg = svg.replace(/<\?xml[^>]*>/gi, "");
  svg = svg.replace(/<!DOCTYPE[^>]*>/gi, "");

  // Remove HTML comments
  svg = svg.replace(/<!--[\s\S]*?-->/g, "");

  // Find first <svg ...> tag
  const idx = svg.toLowerCase().indexOf("<svg");
  if (idx > 0) svg = svg.slice(idx);

  // Remove trailing junk after </svg>
  const endIdx = svg.toLowerCase().lastIndexOf("</svg>");
  if (endIdx > 0) svg = svg.slice(0, endIdx + 6);

  return svg.trim();
}

// ✅ Optional: simple validator
export function looksLikeSvg(s: string): boolean {
  if (!s) return false;
  return /<svg\b/i.test(s);
}
