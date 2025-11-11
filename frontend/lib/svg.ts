// frontend/lib/svg.ts

/**
 * Make an arbitrary SVG string safe to inline in HTML:
 *  - strip xml/doctype
 *  - drop namespace prefixes (e.g. ns0:svg -> svg)
 *  - ensure xmlns + viewBox
 *  - remove fixed width/height and set 100%/100%
 *  - keep large shapes but drop a single full-canvas white backdrop path
 */
export function normalizeSvg(raw: string): string {
  if (!raw) return "";

  let s = String(raw).trim();

  // 1) Strip XML prolog + DOCTYPE
  s = s.replace(/<\?xml[^>]*>/i, "");
  s = s.replace(/<!DOCTYPE[^>]*>/i, "");

  // 2) Convert ns:svg to svg and remove tag prefixes everywhere
  s = s
    .replace(/<\s*([a-z0-9]+:)?svg\b/gi, "<svg")
    .replace(/<\/\s*([a-z0-9]+:)?svg\s*>/gi, "</svg>")
    .replace(/<\s*([a-z0-9]+:)(\w+)/gi, "<$2")
    .replace(/<\/\s*([a-z0-9]+:)(\w+)\s*>/gi, "</$2>");

  // 3) Remove xmlns:* attrs but ensure base xmlns
  s = s.replace(/\sxmlns:[a-zA-Z0-9]+\s*=\s*"[^"]*"/g, "");
  if (!/xmlns=/.test(s)) {
    s = s.replace(/<svg\b/i, '<svg xmlns="http://www.w3.org/2000/svg"');
  }

  // 4) Guarantee viewBox; derive from numeric width/height if needed
  const wh = /<svg[^>]*\bwidth\s*=\s*["']?(\d+(?:\.\d+)?)(?:px)?["'][^>]*\bheight\s*=\s*["']?(\d+(?:\.\d+)?)(?:px)?["']/i.exec(
    s
  );
  const hasViewBox = /<svg[^>]*\bviewBox\s*=\s*["'][^"']+["']/i.test(s);
  if (wh && !hasViewBox) {
    const w = Number(wh[1]);
    const h = Number(wh[2]);
    s = s.replace(/<svg\b/i, `<svg viewBox="0 0 ${w || 100} ${h || 100}"`);
  }

  // 5) Remove fixed width/height; scale to container
  s = s.replace(/<svg\b([^>]*)>/i, (_m, attrs) => {
    let a = attrs
      .replace(/\bwidth\s*=\s*["'][^"']*["']/gi, "")
      .replace(/\bheight\s*=\s*["'][^"']*["']/gi, "")
      .replace(/\s+/g, " ");
    return `<svg${a} width="100%" height="100%" preserveAspectRatio="xMidYMid meet">`;
  });

  // 6) If the very first path is a giant white backdrop, drop it (prevents “white sheet covering everything”)
  // We only remove a fully closed <path> whose fill is an almost-white (#fff, #fefefe, #feffff) and that appears
  // before any other visible shapes.
  s = s.replace(
    /<path[^>]*\bfill\s*=\s*"(?:#fff(?:fff)?|#fefefe|#feffff)"[^>]*>\s*<\/path>\s*/i,
    ""
  );

  return s;
}

/** Useful when you want to preview via <img src=...> instead of inline innerHTML. */
export function dataUrlForSvg(svg: string): string {
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}
