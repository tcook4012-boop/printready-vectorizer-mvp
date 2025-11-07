// frontend/lib/api.ts
export type VectorizeOptions = {
  maxColors: number;            // 2–8
  smoothing: string;            // "precision" | "smooth" | etc.
  primitiveSnap?: boolean;
  minPathArea?: string;
  cornerThreshold?: string;
  filterSpeckle?: string;
};

function looksLikeSvg(s: string) {
  // allow optional XML header then <svg ...>
  return /^\s*(?:<\?xml[^>]*>\s*)?<svg\b/i.test(s);
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

  const res = await fetch(url, {
    method: "POST",
    body: fd,
    headers: {
      // Hint servers to return either JSON or SVG; we'll accept both.
      "Accept": "application/json, image/svg+xml, text/plain;q=0.9, */*;q=0.8",
    },
  });

  const ctype = res.headers.get("content-type") || "";

  // If the server sent raw SVG text
  if (ctype.includes("image/svg+xml") || ctype.startsWith("text/plain")) {
    const text = await res.text();
    if (!res.ok) {
      throw new Error(`Vectorize failed (${res.status}): ${text.slice(0, 180)}`);
    }
    if (!looksLikeSvg(text)) {
      throw new Error(`Bad response from API (not SVG): ${text.slice(0, 180)}`);
    }
    return text;
  }

  // Otherwise try JSON
  let json: any;
  try {
    json = await res.json();
  } catch (e) {
    const fallback = await res.text().catch(() => "");
    throw new Error(
      `Bad response from API (not JSON): ${fallback.slice(0, 180)}`
    );
  }

  if (!res.ok) {
    // Bubble up server error details if present
    const detail = json?.detail ?? json?.error ?? json;
    throw new Error(
      `Vectorize failed (${res.status}): ${typeof detail === "string" ? detail : JSON.stringify(detail)}`
    );
  }

  const svg = json?.svg ?? json?.data ?? json?.body;
  if (!svg || !looksLikeSvg(svg)) {
    throw new Error("Empty or invalid SVG payload from API.");
  }
  return svg;
}
