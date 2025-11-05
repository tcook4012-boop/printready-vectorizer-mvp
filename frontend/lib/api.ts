// frontend/lib/api.ts
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ??
  "https://printready-vectorizer-api.onrender.com";

export type VectorizeOptions = {
  maxColors: number;
  smoothness: "low" | "medium" | "high";
  primitiveSnap: boolean;
};

export async function vectorizeRequest(
  file: File,
  options: VectorizeOptions
): Promise<string> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("max_colors", String(options.maxColors));
  fd.append("smoothness", options.smoothness);
  fd.append("primitive_snap", String(!!options.primitiveSnap));

  const res = await fetch(`${API_BASE}/vectorize`, {
    method: "POST",
    body: fd,
  });

  // Read once; we’ll decide how to interpret it.
  const contentType = res.headers.get("content-type") || "";
  const bodyText = await res.text();

  if (!res.ok) {
    throw new Error(bodyText || `Request failed (${res.status})`);
  }

  // API should return JSON: { svg: "<svg …>" }
  // But if it ever returns raw SVG, handle that too.
  if (contentType.includes("application/json")) {
    let data: any;
    try {
      data = JSON.parse(bodyText);
    } catch {
      throw new Error("Invalid JSON from server.");
    }
    if (!data || typeof data.svg !== "string") {
      throw new Error("Server did not return an SVG string.");
    }
    return data.svg; // ← Already a real SVG string (NOT stringified)
  }

  // Fallback: treat whole body as SVG
  return bodyText;
}

/** Remove XML declaration / DOCTYPE so mounting via innerHTML is safe. */
export function normalizeSvg(svg: string): string {
  const start = svg.search(/<svg[\s\S]*?>/i);
  return start >= 0 ? svg.slice(start) : svg;
}
