export function normalizeSvg(raw: string): string {
  if (!raw) return "";

  let svg = raw
    .replace(/^\s*<\?xml[\s\S]*?\?>\s*/i, "")
    .replace(/^\s*<!DOCTYPE[\s\S]*?>\s*/i, "");

  const m = svg.match(/<svg[\s\S]*<\/svg>/i);
  if (m) svg = m[0];

  // If still no <svg>, just return raw for debugging
  if (!/^<svg[\s>]/i.test(svg)) return raw;

  svg = svg.replace(/\swidth="[^"]*"/i, "").replace(/\sheight="[^"]*"/i, "");

  if (!/xmlns=/.test(svg)) {
    svg = svg.replace(/<svg/i, `<svg xmlns="http://www.w3.org/2000/svg"`);
  }

  if (!/viewBox=/.test(svg)) {
    const w = getNumberAttr(raw, /width="([^"]+)"/i);
    const h = getNumberAttr(raw, /height="([^"]+)"/i);
    if (w && h) svg = svg.replace(/<svg/i, `<svg viewBox="0 0 ${w} ${h}"`);
  }

  if (!/style="/i.test(svg)) {
    svg = svg.replace(
      /<svg/i,
      `<svg style="width:100%;height:100%;" preserveAspectRatio="xMidYMid meet"`
    );
  } else if (!/preserveAspectRatio=/i.test(svg)) {
    svg = svg.replace(/<svg/i, `<svg preserveAspectRatio="xMidYMid meet"`);
  }

  return svg.trim();
}

function getNumberAttr(src: string, re: RegExp): number | null {
  const m = src.match(re);
  if (!m) return null;
  const n = parseFloat(m[1]);
  return Number.isFinite(n) ? n : null;
}
