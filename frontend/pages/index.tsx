// frontend/pages/index.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { vectorize } from "../lib/api";

type Smoothness = "low" | "medium" | "high";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [maxColors, setMaxColors] = useState<number>(8);
  const [smoothness, setSmoothness] = useState<Smoothness>("medium");
  const [svg, setSvg] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  const imgUrl = useMemo(() => (file ? URL.createObjectURL(file) : ""), [file]);
  const downloadRef = useRef<HTMLAnchorElement | null>(null);

  useEffect(() => () => { if (imgUrl) URL.revokeObjectURL(imgUrl); }, [imgUrl]);

  const onChoose = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(""); setSvg("");
    setFile(e.target.files?.[0] || null);
  };

  const onVectorize = async () => {
    setError(""); setSvg("");
    if (!file) { setError("Please choose an image first."); return; }
    try {
      setBusy(true);
      const { svg } = await vectorize({ file, maxColors, smoothness });
      if (!svg) { setError("Received an empty SVG."); return; }
      setSvg(svg);
    } catch (err: any) {
      setError(err?.message || "Vectorization failed.");
    } finally {
      setBusy(false);
    }
  };

  const onDownload = () => {
    if (!svg) return;
    const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = downloadRef.current ?? document.createElement("a");
    a.href = url;
    a.download = (file?.name?.replace(/\.[^.]+$/, "") || "vectorized") + ".svg";
    if (!downloadRef.current) { document.body.appendChild(a); downloadRef.current = a; }
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  };

  return (
    <main style={{ maxWidth: 1180, margin: "40px auto", padding: "0 16px" }}>
      <h1 style={{ marginBottom: 8 }}>PrintReady Vectorizer (MVP)</h1>
      <p style={{ marginTop: 0, color: "#444" }}>
        Upload a logo/image. This calls the potrace vectorizer on the backend.
      </p>

      <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
        <input type="file" accept="image/*" onChange={onChoose} />
        <label>Max Colors{" "}
          <input type="number" min={2} max={16} value={maxColors}
                 onChange={(e) => setMaxColors(Number(e.target.value || 8))}
                 style={{ width: 64 }} />
        </label>
        <label>Smoothness{" "}
          <select value={smoothness} onChange={(e) => setSmoothness(e.target.value as Smoothness)}>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </label>
        <button onClick={onVectorize} disabled={busy || !file} style={{ padding: "8px 14px" }}>
          {busy ? "Processing…" : "Vectorize"}
        </button>
        <button onClick={onDownload} disabled={!svg} style={{ padding: "8px 14px" }}>
          Download SVG
        </button>
      </div>

      {error && (
        <div style={{ marginTop: 16, padding: "10px 12px", background: "#ffecec",
                      color: "#b20000", border: "1px solid #f5c2c2", borderRadius: 6 }}>
          {error}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginTop: 24 }}>
        <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Input Preview</h3>
          {imgUrl ? (
            <img src={imgUrl} style={{ width: "100%", height: "auto", display: "block",
                                       border: "1px solid #eee" }} alt="input preview" />
          ) : <div style={{ color: "#777" }}>No image selected.</div>}
        </section>

        <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Output SVG</h3>
          {svg ? (
            <div style={{ width: "100%", maxHeight: 520, overflow: "auto", border: "1px solid #eee" }}
                 dangerouslySetInnerHTML={{ __html: svg }} />
          ) : (
            <div style={{ color: "#777" }}>No output yet.</div>
          )}
          <pre style={{ marginTop: 12, maxHeight: 200, overflow: "auto",
                        background: "#fafafa", border: "1px solid #eee", padding: 8 }}>
            {JSON.stringify({ svg }, null, 2)}
          </pre>
        </section>
      </div>
    </main>
  );
}
