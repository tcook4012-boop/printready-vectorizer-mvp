// frontend/lib/api.ts
export type VectorizeOptions = {
  maxColors: number;
  primitiveSnap: boolean;
  smoothness?: "low" | "medium" | "high";
  minPathArea?: number;
};

export async function vectorizeImage(
  file: File,
  opts: VectorizeOptions
): Promise<string> {
  const base =
    process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ||
    "https://printready-vectorizer-api.onrender.com";

  const url = `${base}/vectorize`;

  const fd = new FormData();
  fd.append("file", file, file.name);
  fd.append("max_colors", String(opts.maxColors));
  fd.append("primitive_snap", String(!!opts.primitiveSnap));

  if (opts.smoothness) fd.append("smoothness", opts.smoothness);
  if (typeof opts.minPathArea === "number") fd.append("min_path_area", String(opts.minPathArea));

  const res = await fetch(url, {
    method: "POST",
    body: fd,
    headers: { accept: "application/json" },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Vectorize failed (${res.status}): ${text}`);
  }

  const data = await res.json();
  if (!data || typeof data.svg !== "string") {
    throw new Error("Invalid response from API (missing svg)");
  }

  return data.svg;
}
