// lib/api.ts
const API =
  process.env.NEXT_PUBLIC_API_URL || "https://printready-vectorizer-api.onrender.com";

export async function vectorizeImage(
  file: File,
  opts?: { max_colors?: number; smoothness?: string; primitive_snap?: boolean }
): Promise<{ svg: string }> {
  const fd = new FormData();
  fd.append("file", file);
  if (opts?.max_colors != null) fd.append("max_colors", String(opts.max_colors));
  if (opts?.smoothness != null) fd.append("smoothness", String(opts.smoothness));
  if (opts?.primitive_snap != null) fd.append("primitive_snap", String(opts.primitive_snap));

  const res = await fetch(`${API}/vectorize`, {
    method: "POST",
    body: fd, // IMPORTANT: do NOT set Content-Type manually for FormData
  });

  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${t || "request failed"}`);
  }
  return res.json();
}

export async function pingHealth(): Promise<string> {
  const res = await fetch(`${API}/health`);
  return res.text();
}
