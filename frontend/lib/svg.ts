// frontend/lib/svg.ts

/**
 * Quick check: does a string look like SVG markup?
 */
export function looksLikeSvg(markup: string): boolean {
  return /<\s*svg[\s>]/i.test(markup) || /<\s*[\w:]+:svg[\s>]/i.test(markup);
}

/**
 * Normalize SVG markup so it:
 *  - has a plain <svg> root (no ns0:svg etc.)
 *  - removes XML prolog/DOCTYPE
 *  - guarantees a viewBox (so it scales correctly)
 *  - strips explicit width/height so CSS can size it
 *  - removes <script> and on* handlers for safety
 *  - sets preserveAspectRatio="xMidYMid meet"
 *
 * Returns the cleaned SVG as a string. If the input wasn’t SVG,
 * this returns the original string unmodified.
 */
export function normalizeSvg(raw: string): string {
  if (!raw || typeof raw !== "string") return raw;

  let s = raw.trim();

  // Remove XML prolog and DOCTYPE (they can confuse innerHTML)
  s = s.replace(/<\?xml[\s\S]*?\?>/gi, "");
  s = s.replace(/<!DOCTYPE[\s\S]*?>/gi, "");

  // If the tool emitted a namespaced root like <ns0:svg ...>
  // normalize it to a vanilla <svg ...>
  // 1) Opening tag
  s = s.replace(/<\s*([\w-]+):svg([\s>])/i, "<svg$2");
  // 2) Closing tag
  s = s.replace(/<\/\s*([\w-]+):svg\s*>/i, "</svg>");
  // 3) Any other prefixed elements like <ns0:path> -> <path>
  s = s.replace(/<\s*([\w-]+):([a-z0-9_-]+)(\s|>)/gi, "<$2$3");
  s = s.replace(/<\/\s*([\w-]+):([a-z0-9_-]+)\s*>/gi, "</$2>");

  // Now locate the root <svg ...> tag
  const openSvgMatch = s.match(/<\s*svg\b[^>]*>/i);
  if (!openSvgMatch) return raw; // not SVG—return as-is

  let openSvg = openSvgMatch[0];

  // Strip any inline event handlers: onload, onclick, etc.
  openSvg = openSvg.replace(/\s+on[a-z]+\s*=\s*(['"]).*?\1/gi, "");

  // Ensure preserveAspectRatio
  if (!/preserveAspectRatio=/i.test(openSvg)) {
    openSvg = openSvg.replace(
      /<\s*svg/i,
      '<svg preserveAspectRatio="xMidYMid meet"'
    );
  }

  // Extract width/height if present so we can build a viewBox
  const widthMatch = openSvg.match(/\bwidth\s*=\s*['"]?([0-9.]+)(px)?['"]?/i);
  const heightMatch = openSvg.match(/\bheight\s*=\s*['"]?([0-9.]+)(px)?['"]?/i);
  const viewBoxMatch = openSvg.match(/\bviewBox\s*=\s*['"]([^'"]+)['"]/i);

  // If no viewBox, create one from width/height if possible
  if (!viewBoxMatch) {
    const w = widthMatch ? parseFloat(widthMatch[1]) : NaN;
    const h = heightMatch ? parseFloat(heightMatch[1]) : NaN;
    if (isFinite(w) && isFinite(h) && w > 0 && h > 0) {
      openSvg = openSvg.replace(
        /<\s*svg/i,
        `<svg viewBox="0 0 ${w} ${h}"`
      );
    } else {
      // Fallback if we can’t infer—use a square viewBox
      openSvg = openSvg.replace(
        /<\s*svg/i,
        `<svg viewBox="0 0 1024 1024"`
      );
    }
  }

  // Remove explicit width/height so CSS container controls size,
  // and set a safe default style so it lays out nicely.
  openSvg = openSvg
    .replace(/\s+width\s*=\s*['"][^'"]*['"]/gi, "")
    .replace(/\s+height\s*=\s*['"][^'"]*['"]/gi, "");

  if (!/\sstyle=/.test(openSvg)) {
    openSvg = openSvg.replace(
      /<\s*svg/i,
      `<svg style="display:block;max-width:100%;height:auto"`
    );
  }

  // Rebuild the string with the cleaned <svg ...>
  s = s.replace(/<\s*svg\b[^>]*>/i, openSvg);

  // Strip any <script> blocks entirely for safety
  s = s.replace(/<\s*script\b[\s\S]*?<\s*\/\s*script\s*>/gi, "");

  return s;
}
