/**
 * SVG utilities — make SVG safe & embeddable in the DOM.
 * - Accepts raw SVG (with or without XML header/comments)
 * - Handles namespaced tags like <ns0:svg> and <ns0:path>
 * - Ensures root <svg> has a normal xmlns
 * - Optionally enforces a max size to avoid layout explosions
 */

const SVG_XMLNS = "http://www.w3.org/2000/svg";

/** Heuristic: does the text look like SVG (even if namespaced / has XML header/comments)? */
export function looksLikeSvg(txt: string): boolean {
  if (!txt) return false;
  // Allow optional XML header and comments, then a <svg or <nsX:svg start
  return /^\s*(?:<\?xml[^>]*>\s*)?(?:<!--[\s\S]*?-->\s*)*<([a-zA-Z0-9_-]+:)?svg\b/i.test(txt);
}

/** Strip all XML namespace prefixes like ns0:, svg:, xlink:, etc. from *element* names and attributes. */
function stripNamespacePrefixes(svg: string): string {
  let s = svg;

  // 1) Remove xmlns:* declarations entirely (we'll re-add the default xmlns below)
  //    e.g., xmlns:ns0="http://www.w3.org/2000/svg"
  s = s.replace(/\s+xmlns:[a-zA-Z0-9_-]+="[^"]*"/g, "");

  // 2) Remove tag name prefixes on open/close tags: <ns0:path ...> -> <path ...>, </ns0:g> -> </g>
  s = s.replace(/<\/\s*([a-zA-Z0-9_-]+):/g, "</"); // closing tags
  s = s.replace(/<\s*([a-zA-Z0-9_-]+):/g, "<");    // opening tags

  // 3) Remove attribute name prefixes: ns0:href="..." -> href="..."
  s = s.replace(/\s([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)=/g, " $2=");

  return s;
}

/** Ensure the root <svg> tag is present and has a proper default xmlns. */
function ensureDefaultXmlns(svg: string): string {
  // Normalize whitespace on the opening svg tag to check/add xmlns=
  return svg.replace(
    /<svg\b([^>]*)>/i,
    (m, attrs) => {
      const hasXmlns = /\sxmlns\s*=/.test(attrs);
      const cleaned = attrs
        // Remove duplicate width/height if they appear multiple times
        .replace(/\s(width|height)\s*=\s*("[^"]*"|'[^']*')/g, (mm, n, v) => ` ${n}=${v}`)
        .trim();

      return hasXmlns
        ? `<svg ${cleaned}>`
        : `<svg xmlns="${SVG_XMLNS}" ${cleaned}>`;
    }
  );
}

/** Optional: Cap absurdly huge width/height while preserving viewBox if present. */
function capHugeDimensions(svg: string, max = 4000): string {
  // If there's a viewBox, we can safely drop explicit width/height (let CSS control it).
  const hasViewBox = /<svg\b[^>]*\bviewBox\s*=\s*["'][^"']*["']/i.test(svg);
  if (hasViewBox) {
    return svg
      .replace(/\swidth\s*=\s*("[^"]*"|'[^']*')/i, "")
      .replace(/\sheight\s*=\s*("[^"]*"|'[^']*')/i, "");
  }
  // Otherwise clamp numeric width/height if they’re outrageous
  const clamp = (val: string) => {
    const n = parseFloat(val);
    if (Number.isFinite(n) && n > max) return String(max);
    return val;
  };
  return svg
    .replace(/\swidth\s*=\s*"(\d+(?:\.\d+)?)"/i, (_m, v) => ` width="${clamp(v)}"`)
    .replace(/\sheight\s*=\s*"(\d+(?:\.\d+)?)"/i, (_m, v) => ` height="${clamp(v)}"`);
}

/** Remove XML header and leading comments so we can safely innerHTML this. */
function stripXmlPrologAndComments(svg: string): string {
  return svg
    .replace(/^\s*<\?xml[\s\S]*?\?>\s*/i, "")
    .replace(/^\s*<!--[\s\S]*?-->\s*/g, "");
}

/** Full normalization pipeline: robust → plain embeddable <svg> */
export function normalizeSvg(input: string): string {
  if (!input) throw new Error("Empty SVG string.");
  let s = input;

  // Quick pass: if it doesn't look like SVG at all, bail
  if (!looksLikeSvg(s)) {
    throw new Error("API did not return recognizable SVG.");
  }

  // 1) Strip XML header & leading comments
  s = stripXmlPrologAndComments(s);

  // 2) Remove namespace prefixes from tags/attrs, and xmlns:* declarations
  s = stripNamespacePrefixes(s);

  // 3) Ensure default xmlns on root <svg>
  s = ensureDefaultXmlns(s);

  // 4) Tidy dimensions to avoid layout explosions
  s = capHugeDimensions(s, 6000);

  // 5) Final small cleanup: collapse excessive whitespace between tags
  s = s.replace(/>\s+</g, "><").trim();

  // Final sanity: must start with <svg
  if (!/^\s*<svg\b/i.test(s)) {
    throw new Error("Normalized result is not embeddable SVG.");
  }

  return s;
}
