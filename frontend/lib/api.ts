// frontend/lib/api.ts

export type VectorizeOptions = {
  /** Number of colors to keep (1–64). */
  maxColors: number;
  /** Maps to vtracer mode: "smooth" => spline, "sharp" => polygon. */
  smoothing?: "smooth" | "sharp";
  /** Corner threshold (numeric). Higher => fewer sharp corners. */
  cornerThreshold?: number;
  /** Speckle filter size in pixels (removes tiny blobs). */
  filterSpeckle?: number;
  /** Try to preserve thin strokes. */
  thinLines?: boolean;
};

/** Read and validate the API base URL from env. */
function getApiBase(): string {
  const base = process.env.NEXT_PUBLIC_API_BASE?.trim();
  if (!base) {
    throw new Error(
      "Missing NEXT_PUBLIC_API_BASE. Set it in your Vercel/Env or `.env.local`."
    );
  }
  // No trailing slash
  return base.replace(/\/+$/, "");
}

/** Quick sanity: looks like an <svg> root? */
function isSvgRoot(s: string): boolean {
  return /^\s*<\s*svg[\s>]/i.test(s);
}

/**
 * Call the FastAPI /vectorize endpoint and return the SVG string.
 * Throws on any non-2xx or invalid payload.
 */
export async function vectorizeImage(
  file: File,
  opts: VectorizeOptions
): Promise<string> {
  const url = `${getApiBase()}/vectorize`;

  // Build form data in the exact keys our backend expects
  const fd = new FormData();
  fd.append("file", file, file.name);
  fd.append("maxColors", String(opts.maxColors));
  fd.append("smoothing", (opts.smoothing ?? "smooth").toString());

  if (opts.cornerThreshold !== undefined) {
    fd.append("cornerThreshold", String(opts.cornerThreshold));
  }
  if (opts.filterSpeckle !== undefined) {
    fd.append("filterSpeckle", String(opts.filterSpeckle));
  }
  if (opts.thinLines !== undefined) {
    fd.append("thinLines", String(Boolean(opts.thinLines)));
  }

  const res = await fetch(url, {
    method: "POST",
    body: fd,
  });

  // Try to parse JSON either way to surface rich error info
  const raw = await res.text();
  let json: any;
  try {
    json = JSON.parse(raw);
  } catch {
    // Backend should always return JSON. If not, bubble useful text.
    throw new Error(
      `Vectorize failed (${res.status}). Non-JSON response: ${raw.slice(0, 400)}`
    );
  }

  if (!res.ok) {
    // Bubble up the backend's rich error (includes command, stderr, etc.)
    // so you can see exactly which flag failed.
    // eslint-disable-next-line no-console
    console.error("Vectorize failed:", json);
    throw new Error(`Vectorize failed (${res.status}): ${JSON.stringify(json)}`);
  }

  const svg = String(json.svg ?? "");
  if (!svg || !isSvgRoot(svg)) {
    // eslint-disable-next-line no-console
    console.error("Invalid SVG payload from API:", json);
    throw new Error("API returned invalid SVG payload (not an <svg> root).");
  }

  return svg;
}

/** Optional helper to check backend health from the UI/debug panels. */
export async function checkHealth(): Promise<boolean> {
  const url = `${getApiBase()}/health`;
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return false;
    const data = await res.json();
    return Boolean(data?.ok);
  } catch {
    return false;
  }
}
