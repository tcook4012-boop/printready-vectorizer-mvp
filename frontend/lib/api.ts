// frontend/lib/api.ts
export type VectorizeOptions = {
  maxColors: number;
  primitiveSnap: boolean;
  smoothness: "low" | "medium" | "high";
  minPathArea?: number;
  // order is only used by backend; safe to pass through
  order?: "light_to_dark" | "dark_to_light";
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
  fd.append("max_colors", String(opts.maxColors));
  fd.append("primitive_snap", String(opts.primitiveSnap));
  fd.append("smoothness", String(opts.smoothness));
  if (opts.minPathArea != null) fd.append("min_path_area", String(opts.minPathArea));
  if (opts.order) fd.append("order", String(opts.order));

  const res = await fetch(url, { method: "POST", body: fd });

  const ctype = res.headers.get("content-type") || "";

  // Success path
  if (res.ok) {
    // Backends may return application/json {svg: "..."} OR image/svg+xml text
    if (ctype.includes("application/json")) {
      const j = await res.json().catch(() => null);
      if (j && typeof j.svg === "string" && j.svg.includes("<svg")) return j.svg;
      // some tools send the raw svg as body even with json ctype mis-set
      if (j && typeof j === "string" && j.includes("<svg")) return j;
      throw new Error("API returned JSON without an SVG payload.");
    }
    const txt = await res.text();
    if (txt && txt.includes("<svg")) return txt;
    throw new Error("API returned non-SVG response.");
  }

  // Error path: try to surface server message
  let serverMsg = "";
  try {
    if (ctype.includes("application/json")) {
      const j = await res.json();
      serverMsg = j?.error || JSON.stringify(j);
    } else {
      serverMsg = await res.text();
    }
  } catch {}
  throw new Error(`API ${res.status} ${res.statusText}${serverMsg ? ` – ${serverMsg}` : ""}`);
}
