// frontend/pages/index.tsx
import { useMemo, useRef, useState } from "react";
import { vectorize } from "../lib/api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  "https://printready-vectorizer-api.onrender.com";

export default function Home() {
  const fileRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [maxColors, setMaxColors] = useState<number>(8);
  const [smoothness, setSmoothness] = useState<string>("medium");
  const [primitiveSnap, setPrimitiveSnap] = useState<boolean>(true);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [svgText, setSvgText] = useState<string>("");

  const svgBlobUrl = useMemo(() => {
    if (!svgText) return "";
    const blob = new Blob([svgText], { type: "image/svg+xml" });
    return URL.createObjectURL(blob);
  }, [svgText]);

  const onChoose = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] || null;
    setFile(f);
    setSvgText("");
    setError(null);
  };

  const onVectorize = async () => {
    if (!file) {
      setError("Please choose an image file first.");
      return;
    }
    setLoading(true);
    setError(null);
    setSvgText("");

    try {
      const data = await vectorize(API_BASE, file, {
        max_colors: maxColors,
        smoothness,
        primitive_snap: primitiveSnap,
      });

      if ("detail" in data) {
        setError(data.detail || "Vectorization failed.");
      } else if (data.svg && data.svg.trim().length > 0) {
        setSvgText(data.svg);
      } else {
        setError("Got an empty SVG back from the server.");
      }
    } catch (err: any) {
      setError(err?.message || "Failed to fetch");
    } finally {
      setLoading(false);
    }
  };

  const copySvg = async () => {
    if (!svgText) return;
    await navigator.clipboard.writeText(svgText);
    alert("SVG copied to clipboard.");
  };

  return (
    <div style={{ maxWidth: 1200, margin: "40px auto", padding: "0 20px" }}>
      <h1>PrintReady Vectorizer (MVP)</h1>
      <p>Upload a logo/image. This runs a first-party tracer (no Potrace/VTracer).</p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr auto auto auto auto", gap: 12, alignItems: "center", marginBottom: 16 }}>
        <input ref={fileRef} onChange={onChoose} type="file" accept="image/*" />
        <div>
          <div style={{ fontSize: 12 }}>Max Colors</div>
          <input
            type="number"
            min={2}
            max={32}
            value={maxColors}
            onChange={(e) => setMaxColors(Number(e.target.value))}
            style={{ width: 80 }}
          />
        </div>
        <div>
          <div style={{ fontSize: 12 }}>Smoothness</div>
          <select
            value={smoothness}
            onChange={(e) => setSmoothness(e.target.value)}
          >
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </div>
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={primitiveSnap}
            onChange={(e) => setPrimitiveSnap(e.target.checked)}
          />
          Primitive snap
        </label>
        <button onClick={onVectorize} disabled={loading}>
          {loading ? "Processing..." : "Vectorize"}
        </button>
      </div>

      {error && (
        <div style={{ color: "white", background: "#c00", padding: 10, borderRadius: 6, marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignItems: "start" }}>
        {/* Input preview */}
        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
          <h3 style={{ marginTop: 0 }}>Input Preview</h3>
          <div style={{ border: "1px solid #eee", padding: 8, borderRadius: 6, minHeight: 360, display: "grid", placeItems: "center" }}>
            {file ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                alt="input"
                src={URL.createObjectURL(file)}
                style={{ maxWidth: "100%", maxHeight: 420 }}
              />
            ) : (
              <div style={{ color: "#888" }}>No file selected.</div>
            )}
          </div>
        </div>

        {/* Output */}
        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
          <h3 style={{ marginTop: 0 }}>Output SVG</h3>

          {!svgText ? (
            <div style={{ color: "#888" }}>No output yet.</div>
          ) : (
            <>
              {/* Render inline */}
              <div
                style={{
                  border: "1px solid #eee",
                  borderRadius: 6,
                  padding: 8,
                  minHeight: 360,
                  overflow: "auto",
                  background: "#fff",
                }}
                dangerouslySetInnerHTML={{ __html: svgText }}
              />

              <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                <a
                  href={svgBlobUrl}
                  download="vectorized.svg"
                  style={{ padding: "8px 12px", border: "1px solid #ccc", borderRadius: 6, textDecoration: "none" }}
                >
                  Download SVG
                </a>
                <button onClick={copySvg}>Copy SVG</button>
                <details style={{ marginLeft: "auto" }}>
                  <summary>View raw SVG</summary>
                  <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 300, overflow: "auto" }}>
                    {svgText}
                  </pre>
                </details>
              </div>
            </>
          )}
        </div>
      </div>

      <p style={{ marginTop: 24, color: "#666" }}>
        API base: <code>{API_BASE}</code>
      </p>
    </div>
  );
}
