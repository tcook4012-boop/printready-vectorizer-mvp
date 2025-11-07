// frontend/lib/api.ts
export type VectorizeOptions = {
  maxColors: number;
  smoothing: "smooth" | "sharp";
  primitiveSnap?: boolean;         // kept for API compatibility (unused by vtracer)
  cornerThreshold?: string;        // string; we'll coerce on the server
  filterSpeckle?: string;          // string; we'll coerce on the server
};

export async function vectorizeImage(
  file: File,
  opts: VectorizeOptions
): Promise<string> {
  const base = process.env.NEXT_PUBLIC_API_BASE;
  if (!base) throw new Error("Missing NEXT_PUBLIC_API_BASE");

  const url = `${base.replace(/\/$/, "")}/vectorize`;

  const fd = new FormData();
  fd.append("file", file, file.name);
  fd.append("maxColors", String(opts.maxColors));
  fd.append("smoothing", opts.smoothing ?? "smooth");
  fd.append("primitiveSnap", String(Boolean(opts.primitiveSnap)));
  if (opts.cornerThreshold != null) fd.append("cornerThreshold", String(opts.cornerThreshold));
  if (opts.filterSpeckle != null)   fd.append("filterSpeckle", String(opts.filterSpeckle));

  const res = await fetch(url, {
    method: "POST",
    body: fd,
  });

  // If the backend throws, it returns JSON with 'detail'
  const text = await res.text();
  let data: any = null;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`Bad response from API (not JSON): ${text.slice(0, 200)}`);
  }

  if (!res.ok) {
    // Pass through backend diagnostics
    const msg = data?.detail ? JSON.stringify(data.detail) : text;
    throw new Error(msg);
  }

  const svg = data?.svg;
  if (!svg || typeof svg !== "string" || !svg.toLowerCase().includes("<svg")) {
    const snippet = typeof svg === "string" ? svg.slice(0, 200) : "";
    throw new Error(
      JSON.stringify({ error: "Empty SVG payload from server", snippet })
    );
  }

  return svg;
}
