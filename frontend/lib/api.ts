// frontend/lib/api.ts
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  "https://printready-vectorizer-api.onrender.com";

export type Smoothness = "low" | "medium" | "high";

export async function vectorize(params: {
  file: File;
  maxColors?: number;
  smoothness?: Smoothness;
}) {
  const { file, maxColors = 8, smoothness = "medium" } = params;

  const fd = new FormData();
  fd.append("file", file);
  fd.append("max_colors", String(maxColors));
  fd.append("smoothness", smoothness);

  // IMPORTANT: force off until implemented server-side
  fd.append("primitive_snap", "false");

  const res = await fetch(`${API_BASE}/vectorize`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }

  const data = (await res.json()) as { svg?: string };
  const svg = (data.svg ?? "").trim();
  if (!svg) throw new Error("Empty SVG from server");
  return svg;
}
