// lib/api.ts

export type VectorizeOptions = {
  maxColors: number;
  primitiveSnap: boolean;
};

export async function vectorizeImage(
  file: File,
  _opts: VectorizeOptions
): Promise<string> {
  const base = process.env.NEXT_PUBLIC_API_BASE;
  if (!base) throw new Error("Missing NEXT_PUBLIC_API_BASE");

  const url = `${base.replace(/\/$/, "")}/vectorize`;

  const fd = new FormData();
  fd.append("file", file, file.name);

  // Force our backend preset for logo-quality output on small JPEGs
  fd.append("preset", "logo-safe");

  const res = await fetch(url, {
    method: "POST",
    body: fd,
  });

  const text = await res.text();

  if (!res.ok) {
    throw new Error(text || `Vectorization failed (${res.status})`);
  }

  return normalizeSvg(text);
}

// Import normalizeSvg from our SVG helper
import { normalizeSvg } from "./svg";
