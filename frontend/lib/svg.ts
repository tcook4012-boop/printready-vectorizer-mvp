// frontend/lib/svg.ts

/**
 * Takes raw SVG text (possibly with XML prolog and DOCTYPE from Potrace/VTracer)
 * and returns a clean, embeddable <svg>…</svg> string you can innerHTML into a div.
 */
export function normalizeSvg(raw: string): string {
  if (!raw) return "";

  // 1) Trim and remove XML prolog and DOCTYPE (Potrace adds these)
  let svg = raw
    .replace(/^\s*<\?xml[\s\S]*?\?>\s*/i, "")           // <?xml ... ?>
    .replace(/^\s*<!DOCTYPE[\s\S]*?>\s*/i, "");          // <!DOCTYPE ...>

  // 2) Extract the <svg>…</svg> block just in case extra noise is around
  const match = svg.match(/<svg[\s\S]*<\/svg>/i);
  if (match) svg = match[0];

  // 3) Ensure it’s actually an <svg>
  if (!/^<svg[\s>]/i.test(svg)) return "";

  // 4) Remove hardcoded width/height so it can scale in our container
  svg = svg
    .replace(/\swidth="[^"]*"/i, "")
    .replace(/\sheight="[^"]*"/i, "");

  // 5) Guarantee xmlns and viewBox exist; if there's no viewBox, try to build one
  if (!/xmlns=/.test(svg)) {
    svg = svg.replace(
      /<svg/i,
      `<svg xmlns="http://www.w3.org/2000/svg"`
    );
  }

  if (!/viewBox=/.test(svg)) {
    // Try to read from width/height that we may still find elsewhere
    const w = getNumberAttr(raw, /width="([^"]+)"/i);
    const h = getNumberAttr(raw, /height="([^"]+)"/i);
    if (w && h) {
      svg = svg.replace(/<svg/i, `<svg viewBox="0 0 ${w} ${h}"`);
    } else {
      // fallback — many Potrace/VTracer svgs render fine without; leave as-is
    }
  }

  // 6) Make it responsive & preserve aspect ratio nicely
  // Add inline style for 100% sizing if not already present
  if (!/style="/i.test(svg)) {
    svg = svg.replace(
      /<svg/i,
      `<svg style="width:100%;height:100%;" preserveAspectRatio="xMidYMid meet"`
    );
  } else {
    // Ensure preserveAspectRatio exists even if style already present
    if (!/preserveAspectRatio=/i.test(svg)) {
      svg = svg.replace(
        /<svg/i,
        `<svg preserveAspectRatio="xMidYMid meet"`
      );
    }
  }

  return svg.trim();
}

function getNumberAttr(src: string, re: RegExp): number | null {
  const m = src.match(re);
  if (!m) return null;
  const n = parseFloat(m[1]);
  return Number.isFinite(n) ? n : null;
}
