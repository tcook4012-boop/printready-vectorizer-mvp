// frontend/lib/api.ts
export type VectorizeResponse =
  | { svg: string }
  | { detail: string };

export async function vectorize(
  apiBase: string,
  file: File,
  opts: {
    max_colors: number;
    smoothness: string;
    primitive_snap: boolean;
  }
): Promise<VectorizeResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("max_colors", String(opts.max_colors));
  form.append("smoothness", String(opts.smoothness));
  form.append("primitive_snap", String(opts.primitive_snap));

  const res = await fetch(`${apiBase}/vectorize`, {
    method: "POST",
    body: form,
  });

  // FastAPI returns JSON for both success and error
  return res.json();
}
