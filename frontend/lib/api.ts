export type VectorizeOptions = {
  maxColors: number;
  smoothing?: "smooth" | "sharp";
  primitiveSnap?: boolean;
  minPathArea?: string;     // optional, passed through if you add it later
  mode?: "color" | "binary";
  thinLines?: boolean;
  cornerThreshold?: string; // e.g. "10"
  filterSpeckle?: number;   // e.g. 4
};

const API_BASE =
  (process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/+$/, "");

function cleanSvg(svg: string): string {
  // strip BOM, XML prolog, and DOCTYPE — some normalizers choke on these
  return svg
    .replace(/^\uFEFF/, "")
    .replace(/<\?xml[^>]*\?>\s*/i, "")
    .replace(/<!DOCTYPE[^>]*>\s*/i, "")
    .trim();
}

function looksLikeSvgRoot(s: string): boolean {
  return /^<\s*svg[\s>]/i.test(s);
}

export async function vectorizeImage(
  file: File,
  opts: VectorizeOptions
): Promise<string> {
  if (!API_BASE) throw new Error("Missing NEXT_PUBLIC_API_BASE");

  const url = `${API_BASE}/vectorize`;
  const fd = new FormData();
  fd.append("file", file, file.name);
  fd.append("maxColors", String(opts.maxColors));
  fd.append("smoothing", opts.smoothing ?? "smooth");
  fd.append("primitiveSnap", String(Boolean(opts.primitiveSnap)));
  if (opts.cornerThreshold) fd.append("cornerThreshold", String(opts.cornerThreshold));
  if (typeof opts.filterSpeckle === "number") fd.append("filterSpeckle", String(opts.filterSpeckle));
  if (typeof opts.thinLines === "boolean") fd.append("thinLines", String(opts.thinLines));

  const res = await fetch(url, { method: "POST", body: fd });
  const text = await res.text();

  // Try JSON first
  let payload: any = null;
  try {
    payload = JSON.parse(text);
  } catch {
    // Not JSON — maybe the backend returned raw SVG (shouldn't, but be resilient)
    const maybeSvg = cleanSvg(text);
    if (looksLikeSvgRoot(maybeSvg)) return maybeSvg;
    throw new Error(`Unexpected response type: ${text.slice(0, 120)}…`);
  }

  if (!res.ok) {
    // backend sent an error object
    const msg =
      (payload && (payload.error || payload.detail?.error)) ||
      `HTTP ${res.status}`;
    throw new Error(String(msg));
  }

  if (!payload || typeof payload.svg !== "string") {
    throw new Error(
      `Backend returned non-SVG: ${JSON.stringify(payload).slice(0, 200)}…`
    );
  }

  const cleaned = cleanSvg(payload.svg);
  if (!looksLikeSvgRoot(cleaned)) {
    // Show a tiny preview in the error so we can debug
    throw new Error(
      `normalizeSvg: not an <svg> root. Received: ${cleaned.slice(0, 200)}…`
    );
  }

  return cleaned;
}
