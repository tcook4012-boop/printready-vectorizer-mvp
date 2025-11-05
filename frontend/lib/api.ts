// frontend/lib/api.ts
const BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  "https://printready-vectorizer-api.onrender.com";

export type VectorizeParams = {
  file: File;
  maxColors: number;
  smoothness: "low" | "medium" | "high";
};

export type VectorizeResponse = { svg: string };

export async function vectorize({
  file,
  maxColors,
  smoothness,
}: VectorizeParams): Promise<VectorizeResponse> {
  const form = new FormData();
  form.append("file", file, file.name);           // IMPORTANT: keep as File with name
  form.append("max_colors", String(maxColors));
  form.append("smoothness", smoothness);
  form.append("primitive_snap", "false");         // HARD FORCE POTRACE PATH

  const res = await fetch(`${BASE}/vectorize`, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Vectorize failed ${res.status}: ${text}`);
  }
  const data = (await res.json()) as VectorizeResponse;
  return { svg: (data?.svg || "").trim() };
}
