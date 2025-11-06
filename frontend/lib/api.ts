// frontend/lib/api.ts

export interface VectorizeOptions {
  maxColors: number;
  primitiveSnap: boolean;
}

// ✅ Safe fallback if NEXT_PUBLIC_API_BASE is not set
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  "https://printready-vectorizer-api.onrender.com";

export async function vectorizeImage(
  file: File,
  opts: VectorizeOptions
): Promise<string> {
  const base = API_BASE.replace(/\/$/, ""); // remove trailing slash if present
  const url = `${base}/vectorize`;

  const fd = new FormData();
  fd.append("file", file, file.name);
  fd.append("max_colors", String(opts.maxColors));
  fd.append("primitive_snap", String(opts.primitiveSnap));

  let res: Response;

  try {
    res = await fetch(url, {
      method: "POST",
      body: fd,
    });
  } catch (err) {
    console.error("Fetch error:", err);
    throw new Error("Failed to reach vectorization server");
  }

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    console.error("Bad response:", res.status, txt);
    throw new Error(`Vectorization failed: ${res.status} - ${txt}`);
  }

  // backend returns JSON { svg: "<svg>..." }
  const data = await res.json().catch(() => null);

  if (!data || !data.svg) {
    console.error("Unexpected response:", data);
    throw new Error("Unexpected server response");
  }

  return data.svg;
}
