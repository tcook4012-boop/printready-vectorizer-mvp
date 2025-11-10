export type VectorizeOptions = {
  maxColors: number;
  primitiveSnap: boolean;
  smoothness: "low" | "medium" | "high";
  minPathArea: number;
  order: "light_to_dark" | "dark_to_light";
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
  fd.append("smoothness", opts.smoothness);
  fd.append("min_path_area", String(opts.minPathArea));
  fd.append("order", opts.order);

  const res = await fetch(url, { method: "POST", body: fd });

  // Always read as text once, then branch
  const contentType = res.headers.get("content-type") || "";
  const bodyText = await res.text();

  // Non-2xx: try to surface useful error info
  if (!res.ok) {
    try {
      const j = JSON.parse(bodyText);
      if (j?.svg) return String(j.svg);
      if (j?.error) throw new Error(String(j.error) + (j?.stderr ? `\n${j.stderr}` : ""));
    } catch {
      /* not json */
    }
    throw new Error(`API ${res.status}: ${bodyText.slice(0, 500)}`);
  }

  // JSON path
  if (contentType.includes("application/json")) {
    try {
      const j = JSON.parse(bodyText);
      if (j?.svg) return String(j.svg);
      if (j?.error) throw new Error(String(j.error));
      throw new Error('JSON response missing "svg" property');
    } catch {
      throw new Error(`Bad JSON from API: ${bodyText.slice(0, 500)}`);
    }
  }

  // Otherwise treat it as raw SVG
  return bodyText;
}
