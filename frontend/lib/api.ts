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
  return base.replace(/\/+$/, "");
}

/** Extract a valid <svg>…</svg> from a string that may contain prolog/comments. */
function normalizeSvg(raw: string): string {
  if (!raw) throw new Error("Empty SVG payload.");

  // Find the first real <svg ...> tag (allow leading XML/doctype/comments/whitespace)
  const startMatch = raw.match(/<svg[\s>]/i);
  if (!startMatch || startMatch.index == null) {
    throw new Error("API returned payload without an <svg> root.");
  }
  const start = startMatch.index;

  // Try to find a corresponding </svg> end tag; if not found, return from <svg> to end.
  const endMatch = raw.match(/<\/svg\s*>/i);
  let end: number | undefined = undefined;
  if (endMatch && endMatch.index != null) {
    end = endMatch.index + endMatch[0].length;
  }

  const svg = raw.slice(start, end).trim();
  // Quick sanity check that the slice starts with <svg
  if (!/^\s*<svg[\s>]/i.test(svg)) {
    throw new Error("Normalized SVG does not start with <svg>.");
  }
  return svg;
}

/**
 * Call the FastAPI /vectorize endpoint and return a normalized SVG string.
 */
export async function vectorizeImage(
  file: File,
  opts: VectorizeOptions
): Promise<string> {
  const url = `${getApiBase()}/vectorize`;

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

  const res = await fetch(url, { method: "POST", body: fd });

  const rawText = await res.text();
  let payload: any;
  try {
    payload = JSON.parse(rawText);
  } catch {
    // Non-JSON response: still try to normalize to SVG (some proxies can strip headers)
    try {
      return normalizeSvg(rawText);
    } catch {
      throw new Error(
        `Vectorize failed (${res.status}). Non-JSON response:\n${rawText.slice(0, 400)}`
      );
    }
  }

  if (!res.ok) {
    // Surface the backend JSON error (it includes stderr/cmd)
    // eslint-disable-next-line no-console
    console.error("Vectorize failed:", payload);
    // If backend included a snippet, append it for quick debugging.
    const snippet = payload?.snippet
      ? `\n\nsnippet:\n${String(payload.snippet).slice(0, 300)}`
      : "";
    throw new Error(
      `Vectorize failed (${res.status}): ${JSON.stringify(payload)}${snippet}`
    );
  }

  const svgRaw = String(payload.svg ?? "");
  return normalizeSvg(svgRaw);
}

/** Optional health check for a debug panel. */
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
