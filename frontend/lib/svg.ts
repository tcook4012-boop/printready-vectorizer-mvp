// lib/svg.ts

export function normalizeSvg(svg: string): string {
  if (!svg) return "";

  // Remove BOM, XML prolog, DOCTYPE, and comments
  let cleaned = svg
    .replace(/^\uFEFF/, "")
    .replace(/<\?xml[^>]*\?>/gi, "")
    .replace(/<!DOCTYPE[^>]*>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .trim();

  // Ensure it actually contains <svg>
  if (!/<svg[\s>]/i.test(cleaned)) {
    throw new Error("SVG parse error: output does not contain <svg>");
  }

  // Add viewBox if missing (helps scaling)
  if (!/viewBox=/i.test(cleaned)) {
    cleaned = cleaned.replace(
      /<svg([^>]*)>/i,
      (match, attrs) => {
        const widthMatch = attrs.match(/width="([^"]+)"/i);
        const heightMatch = attrs.match(/height="([^"]+)"/i);
        if (widthMatch && heightMatch) {
          const w = parseFloat(widthMatch[1]);
          const h = parseFloat(heightMatch[1]);
          if (!isNaN(w) && !isNaN(h)) {
            return `<svg${attrs} viewBox="0 0 ${w} ${h}">`;
          }
        }
        return match;
      }
    );
  }

  return cleaned;
}
