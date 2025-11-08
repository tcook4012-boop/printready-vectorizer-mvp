// frontend/lib/api.ts

export type VectorizeOptions = {
  maxColors: number;
  smoothing: string;              // "precision" | "smooth"
  primitiveSnap?: boolean;
  minPathArea?: string;
  cornerThreshold?: string;
  filterSpeckle?: string;
  // Optional engine controls
  engine?: "auto" | "vtracer" | "potrace";
  threshold?: number | string;    // Potrace threshold % (0..100)
};

// Accept XML header, comments, and optional DOCTYPE before <svg>
function looksLikeSvg(s: string) {
  return /^\s*(?:<\?xml[^>]*>\s*)?(?:<!--[\s\S]*?-->\s*)*(?:<!DOCTYPE[\s\S]*?>\s*)?<svg\b/i.test(
    s
  );
}

export async function vectorizeImage(
  file: File,
  opts: VectorizeOptions
): Promise<string> {
  const base = process.env.NEXT_PUBLIC_API_BASE;
  if (!base) throw new Error("Missing NEXT_PUBLIC_API_BASE");

  const url = `${base.replace(/\/$/, "")}/vectorize`;

  const fd = new FormData();
  fd.append("file", file, file.name);
  fd.append("max_colors", String(opts.maxColors));
  fd.append("smoothing", String(opts.smoothing ?? "precision"));
  if (opts.primitiveSnap != null) fd.append("primitive_snap", String(!!opts.primitiveSnap));
  if (opts.minPathArea != null) fd.append("min_path_area", String(opts.minPathArea));
  if (opts.cornerThreshold != null) fd.append("corner_threshold", String(opts.cornerThreshold));
  if (opts.filterSpeckle != null) fd.append("filter_speckle", String(opts.filterSpeckle));
  if (opts.engine) fd.append("engine", String(opts.engine));
  if (opts.threshold != null) fd.append("threshold", String(opts.threshold));

  const res = await fetch(url, {
    method: "POST",
    body: fd,
    headers: {
      // Ask for SVG or plain text first; JSON only for error payloads
      Accept: "image/svg+xml, text/plain;q=0.9, application/json;q=0.5, */*;q=0.1",
    },
  });

  const ctype = (res.headers.get("content-type") || "").toLowerCase();
  const bodyText = await res.text();

  // If server says it's SVG, accept it outright
  if (ctype.includes("image/svg+xml")) {
    if (!res.ok) {
      throw new Error(`Vectorize failed (${res.status}): ${bodyText.slice(0, 220)}`);
    }
    return bodyText;
  }

  // Some servers return text/plain for XML; detect by content
  if (ctype.startsWith("text/plain") || looksLikeSvg(bodyText)) {
    if (!res.ok) {
      throw new Error(`Vectorize failed (${res.status}): ${bodyText.slice(0, 220)}`);
    }
    if (!looksLikeSvg(bodyText)) {
      throw new Error(`Bad response from API (not SVG): ${bodyText.slice(0, 220)}`);
    }
    return bodyText;
  }

  // Probably a JSON error payload
  let json: any;
  try {
    json = JSON.parse(bodyText);
  } catch {
    throw new Error(`Bad response from API (not SVG/JSON): ${bodyText.slice(0, 220)}`);
  }

  if (!res.ok) {
    const detail = json?.detail ?? json?.error ?? json;
    throw new Error(
      `Vectorize failed (${res.status}): ${
        typeof detail === "string" ? detail : JSON.stringify(detail)
      }`
    );
  }

  const svg = json?.svg ?? json?.data ?? json?.body;
  if (!svg || !looksLikeSvg(svg)) throw new Error("Empty SVG payload.");
  return svg;
}
