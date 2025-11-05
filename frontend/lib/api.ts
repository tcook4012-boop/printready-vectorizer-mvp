// lib/api.ts
export type VectorizeOptions = {
  maxColors: number;          // 1..8
  primitiveSnap: boolean;     // true/false
};

export async function vectorizeImage(
  file: File,
  opts: VectorizeOptions
): Promise<string> {
  const base = process.env.NEXT_PUBLIC_API_BASE;
  if (!base) throw new Error("Missing NEXT_PUBLIC_API_BASE");

  const url = `${base.replace(/\/$/, "")}/vectorize`;

  const fd = new FormData();
  fd.append("file", file, file.name);
  fd.append("max_colors", String(opts.maxColors));
  fd.append("primitive_snap", String(opts.primitiveSnap));

  const res = await fetch(url, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Vectorize failed: ${res.status} ${text}`);
  }

  // API returns: { svg: "<svg ...>...</svg>" }
  const data = (await res.json()) as { svg?: string; detail?: unknown };
  if (!data?.svg || !data.svg.includes("<svg")) {
    throw new Error(
      `Unexpected response: ${JSON.stringify(data).slice(0, 400)}`
    );
  }
  return data.svg;
}
