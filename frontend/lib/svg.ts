// frontend/lib/svg.ts

/**
 * Strip any namespace prefixes (e.g. ns0:svg, ns0:path, xlink:href),
 * ensure a proper <svg ... viewBox="...">, and remove conflicting width/height
 * so CSS can control the preview box.
 */
export function normalizeSvg(raw: string): string {
  if (!raw) return "";

  let s = String(raw).trim();

  // 1) If the API sent JSON instead of raw SVG, bail early
  if (s.startsWith("{") || s.startsWith("[")) return "";

  // 2) Keep only the outermost <svg ...>...</svg>
  const svgOpen = s.search(/<\s*([a-zA-Z0-9:_-]+)\s*[^>]*>/);
  const svgClose = s.search(/<\/\s*svg\s*>/i);
  if (svgOpen === -1 || svgClose === -1) return "";

  s = s.slice(svgOpen, svgClose + "</svg>".length);

  // 3) Replace any "<ns0:svg" (or similar) with "<svg"
  s = s.replace(/<\s*[a-zA-Z_]\w*:\s*svg\b/gi, "<svg");
  s = s.replace(/<\/\s*[a-zA-Z_]\w*:\s*svg\s*>/gi, "</svg>");

  // 4) Remove namespace prefixes from *all* element tags like <ns1:path> → <path>
  s = s.replace(/<\s*\/\s*([a-zA-Z_]\w*):/g, "</"); // closing tags
  s = s.replace(/<\s*([a-zA-Z_]\w*):/g, "<");       // opening tags

  // 5) Remove namespace prefixes from attribute names: ns1:href="..." → href="..."
  s = s.replace(/\s([a-zA-Z_]\w*):([a-zA-Z_][\w.-]*)=/g, " $2=");

  // 6) Drop xmlns:* declarations; keep (or add) the base xmlns
  s = s.replace(/\sxmlns:[a-zA-Z_]\w*="[^"]*"/g, "");
  if (!/\sxmlns=/.test(s)) {
    s = s.replace(/<svg\b/, '<svg xmlns="http://www.w3.org/2000/svg"');
  }

  // 7) Ensure we have a viewBox. If missing, synthesize it from width/height (numbers only).
  const hasViewBox = /\sviewBox\s*=\s*"/i.test(s);
  const wMatch = s.match(/\swidth\s*=\s*"([\d.]+)"/i);
  const hMatch = s.match(/\sheight\s*=\s*"([\d.]+)"/i);

  if (!hasViewBox) {
    const w = wMatch ? Number(wMatch[1]) : undefined;
    const h = hMatch ? Number(hMatch[1]) : undefined;
    if (Number.isFinite(w) && Number.isFinite(h) && w! > 0 && h! > 0) {
      s = s.replace(/<svg\b/, `<svg viewBox="0 0 ${w} ${h}"`);
    } else {
      // Fallback if we can't parse width/height
      s = s.replace(/<svg\b/, `<svg viewBox="0 0 1000 1000"`);
    }
  }

  // 8) Remove width/height attributes so the preview container can size it.
  s = s.replace(/\swidth\s*=\s*"[^"]*"/gi, "");
  s = s.replace(/\sheight\s*=\s*"[^"]*"/gi, "");

  // 9) Some generators emit XML declaration/doctype—strip them (React innerHTML-safe)
  s = s.replace(/<\?xml[^>]*>/gi, "");
  s = s.replace(/<!DOCTYPE[^>]*>/gi, "");

  return s.trim();
}

/**
 * Optional: wrap the SVG with a scale transform (not strictly needed now,
 * but handy if you later add zoom controls by multiplying a scale factor).
 */
export function wrapForPreview(svg: string): string {
  if (!svg) return "";
  // Insert a group after <svg ...>
  return svg.replace(
    /<svg\b([^>]*)>/i,
    (_m, attrs) => `<svg ${attrs}><g id="preview-root">`
  ).replace(/<\/svg>\s*$/i, "</g></svg>");
}
