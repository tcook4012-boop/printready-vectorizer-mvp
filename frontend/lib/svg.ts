// frontend/lib/svg.ts

/**
 * Aggressively normalize possibly-namespaced SVG strings so they can be
 * injected with dangerouslySetInnerHTML and scaled by CSS.
 */
export function normalizeSvg(raw: string): string {
  if (!raw) return "";

  let s = String(raw).trim();

  // Bail if it looks like JSON (API error body etc.)
  if (s.startsWith("{") || s.startsWith("[")) return "";

  // Keep only the outermost <svg ...>...</svg>
  const firstSvgOpen = s.search(/<\s*([a-zA-Z0-9:_-]+)\b[^>]*>/);
  const lastSvgClose = s.search(/<\/\s*svg\s*>/i);
  if (firstSvgOpen === -1 || lastSvgClose === -1) return "";
  s = s.slice(firstSvgOpen, lastSvgClose + "</svg>".length);

  // --- Namespace removal (tags) ---
  // <ns0:svg> -> <svg>  and </ns0:svg> -> </svg>
  s = s.replace(/<\s*[a-zA-Z_][\w.-]*:\s*svg\b/gi, "<svg");
  s = s.replace(/<\/\s*[a-zA-Z_][\w.-]*:\s*svg\s*>/gi, "</svg>");

  // Any other namespaced elements: <nsX:anything ...> -> <anything ...>
  // Closing tags:
  s = s.replace(/<\s*\/\s*([a-zA-Z_][\w.-]*):/g, "</");
  // Opening/self-closing tags:
  s = s.replace(/<\s*([a-zA-Z_][\w.-]*):/g, "<");

  // --- Namespace removal (attributes) ---
  // nsX:href="..." -> href="..."
  s = s.replace(/\s([a-zA-Z_][\w.-]*):([a-zA-Z_][\w.-]*)=/g, " $2=");

  // Drop explicit xmlns:* attributes; keep/add base xmlns
  s = s.replace(/\sxmlns:[a-zA-Z_][\w.-]*="[^"]*"/g, "");
  if (!/\sxmlns\s*=/.test(s)) {
    s = s.replace(/<svg\b/i, '<svg xmlns="http://www.w3.org/2000/svg"');
  }

  // Ensure we have a viewBox; derive from numeric width/height if present
  const hasViewBox = /\sviewBox\s*=\s*"/i.test(s);
  const wMatch = s.match(/\swidth\s*=\s*"([\d.]+)"/i);
  const hMatch = s.match(/\sheight\s*=\s*"([\d.]+)"/i);
  if (!hasViewBox) {
    const w = wMatch ? Number(wMatch[1]) : undefined;
    const h = hMatch ? Number(hMatch[1]) : undefined;
    if (Number.isFinite(w) && Number.isFinite(h) && w! > 0 && h! > 0) {
      s = s.replace(/<svg\b/i, `<svg viewBox="0 0 ${w} ${h}"`);
    } else {
      s = s.replace(/<svg\b/i, `<svg viewBox="0 0 1000 1000"`);
    }
  }

  // Remove fixed width/height so the preview container can size it
  s = s.replace(/\swidth\s*=\s*"[^"]*"/gi, "");
  s = s.replace(/\sheight\s*=\s*"[^"]*"/gi, "");

  // Strip XML header/doctype if present
  s = s.replace(/<\?xml[^>]*>/gi, "");
  s = s.replace(/<!DOCTYPE[^>]*>/gi, "");

  return s.trim();
}

/**
 * Optional wrapper if you later need a zoom group.
 */
export function wrapForPreview(svg: string): string {
  if (!svg) return "";
  return svg
    .replace(/<svg\b([^>]*)>/i, (_m, attrs) => `<svg ${attrs}><g id="preview-root">`)
    .replace(/<\/svg>\s*$/i, "</g></svg>");
}
