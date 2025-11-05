// frontend/lib/api.ts
const BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  "https://printready-vectorizer-api.onrender.com";

export type VectorizeParams = {
  file: File;
  maxColors: number;
  smoothness: "low" | "medium" | "high";
  // We keep the flag here for UI completeness, but the working backend path is primitive_snap=false
  primitiveSnap: boolean;
};

export type VectorizeResponse = {
  svg: string;
};

export async function vectorize({
  file,
  maxColors,
  smoothness,
  primitiveSnap,
}: VectorizeParams): Promise<VectorizeResponse> {
  const form = new FormData();
  // IMPORTANT: ensure we send a File (not just a Blob) so FastAPI sees `filename` and content-type
  form.append("file", file, file.name);
  form.append("max_colors", String(maxColors));
  form.append("smoothness", smoothness);

  // The working tracer is the potrace path → primitive_snap=false
  // If/when you implement the primitive route, you can pass the real value instead.
  form.append("primitive_snap", String(false));

  const res = await fetch(`${BASE}/vectorize`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Vectorize failed ${res.status}: ${text}`);
  }

  const data = (await res.json()) as VectorizeResponse;

  // Defensive: normalize SVG string
  const svg = (data?.svg ?? "").trim();
  return { svg };
}
