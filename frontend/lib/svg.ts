// Simple SVG post-processing helpers for cleaner output in preview/download.

export type CleanOptions = {
  removeTiny: boolean;         // drop <path> with very tiny bbox (approx via length heuristic)
  minPathLen: number;          // characters threshold for 'd' attr (proxy for tiny fragments)
  trimPrecision: number;       // decimal precision clamp for numbers in path data
  removeComments: boolean;
  collapseWhitespace: boolean;
};

const DEFAULTS: CleanOptions = {
  removeTiny: true,
  minPathLen: 8,
  trimPrecision: 3,
  removeComments: true,
  collapseWhitespace: true,
};

const numRe = /(-?\d*\.\d+|-?\d+)/g;

function clampPrecision(pathD: string, precision: number) {
  return pathD.replace(numRe, (m) => {
    const n = Number(m);
    if (Number.isNaN(n)) return m;
    return Number(n.toFixed(precision)).toString();
  });
}

export function cleanSvg(svgText: string, opts?: Partial<CleanOptions>): string {
  const o = { ...DEFAULTS, ...(opts || {}) };
  let s = svgText;

  if (o.removeComments) {
    s = s.replace(/<!--[\s\S]*?-->/g, "");
  }

  // Collapse whitespace between tags and in attributes
  if (o.collapseWhitespace) {
    s = s.replace(/\s{2,}/g, " ");
    s = s.replace(/>\s+</g, "><");
  }

  // Trim path precision + remove tiny paths
  // Note: We use a simple character-length heuristic for 'd' attribute to avoid DOM parsing.
  s = s.replace(/(<path\b[^>]*\sd=")([^"]*)("[^>]*>)/gi, (_m, pre, d, post) => {
    let nd = clampPrecision(d, o.trimPrecision);
    if (o.removeTiny && nd.replace(/[MLCZmlcz\s,.-]/g, "").length < o.minPathLen) {
      // Convert to comment marker to keep structure consistent
      return `<!-- removed tiny path -->`;
    }
    return `${pre}${nd}${post}`;
  });

  // Remove empty groups
  s = s.replace(/<g[^>]*>\s*<\/g>/gi, "");

  // Ensure xmlns present (helpful when backend served as text/plain)
  if (!/^\s*<svg[^>]*xmlns=/.test(s)) {
    s = s.replace(
      /^\s*<svg\b/,
      `<svg xmlns="http://www.w3.org/2000/svg"`
    );
  }

  return s.trim();
}
