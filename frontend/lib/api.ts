export async function vectorizeImage(
  file: File,
  opts: {
    maxColors: number;
    smoothing: string;
    primitiveSnap?: boolean;
    minPathArea?: string;
    mode?: string;
    thinLines?: boolean;
    cornerThreshold?: string;
  }
): Promise<string> {
  const base = process.env.NEXT_PUBLIC_API_BASE;
  if (!base) throw new Error("Missing NEXT_PUBLIC_API_BASE");

  const url = `${base.replace(/\/$/, "")}/vectorize`;

  const fd = new FormData();
  fd.append("file", file);

  // High-quality tracing settings
  fd.append("colors", String(opts.maxColors || 6));
  fd.append("mode", "color");
  fd.append("smoothing", "precision");
  fd.append("thin_lines", "true");
  fd.append("corner_threshold", opts.cornerThreshold || "0.05");

  const res = await fetch(url, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Vectorize failed (frontend): ${text}`);
  }

  const data = await res.json();
  return data.svg;
}
