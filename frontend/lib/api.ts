// frontend/lib/api.ts
export type VectorizeOptions = {
  maxColors: number;                // 2-8
  primitiveSnap: boolean;           // kept for UI parity (backend ignores for now)
  minPathArea: number;              // fraction, e.g. 0.0002
  layerOrder: "light_to_dark" | "dark_to_light";
};

function getApiBase(): string {
  // Use env if present, otherwise fall back to the Render URL.
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE?.trim();
  return (fromEnv && fromEnv.length > 0)
    ? fromEnv
    : "https://printready-vectorizer-api.onrender.com";
}

export async function vectorizeImage(
  file: File,
  opts: VectorizeOptions
): Promise<string> {
  const API_BASE = getApiBase();
  const url = `${API_BASE.replace(/\/$/, "")}/vectorize`;

  const fd = new FormData();
  fd.append("file", file, file.name);
  fd.append("max_colors", String(opts.maxColors));
  fd.append("primitive_snap", String(opts.primitiveSnap));
  // IMPORTANT: these key names must match the backend
  fd.append("min_area_frac", String(opts.minPathArea));
  fd.append("layer_order", opts.layerOrder);

  const res = await fetch(url, {
    method: "POST",
    body: fd,
  });

  // Helpful error surfacing for 4xx/5xx
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `Vectorize API ${res.status}. ${text || "Request failed."}`
    );
  }

  // Backend returns JSON { svg: "<svg...>" }
  const data = await res.json();
  if (!data || typeof data.svg !== "string") {
    throw new Error("Unexpected response: missing { svg }");
  }
  return data.svg;
}
