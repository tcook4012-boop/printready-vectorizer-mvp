// app/page.tsx
"use client";

import { useMemo, useRef, useState } from "react";
import { vectorizeImage } from "../lib/api";

export default function HomePage() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const [maxColors, setMaxColors] = useState(4);       // default > 1 so you see color
  const [primitiveSnap, setPrimitiveSnap] = useState(false);

  const [svgMarkup, setSvgMarkup] = useState<string>("");
  const [error, setError] = useState<string>("");

  const downloadRef = useRef<HTMLAnchorElement | null>(null);

  const onChoose: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f || null);
    setSvgMarkup("");
    setError("");

    if (previewUrl) URL.revokeObjectURL(previewUrl);
    if (f) setPreviewUrl(URL.createObjectURL(f));
    else setPreviewUrl(null);
  };

  const onVectorize = async () => {
    try {
      setError("");
      setSvgMarkup("");
      if (!file) {
        setError("Please choose an image file first.");
        return;
      }
      const svg = await vectorizeImage(file, {
        maxColors,
        primitiveSnap,
      });
      setSvgMarkup(svg);
    } catch (err: any) {
      setError(err?.message ?? String(err));
    }
  };

  const downloadHref = useMemo(() => {
    if (!svgMarkup) return "";
    const blob = new Blob([svgMarkup], { type: "image/svg+xml" });
    return URL.createObjectURL(blob);
  }, [svgMarkup]);

  return (
    <main style={{ padding: "18px", fontFamily: "Inter, system-ui, sans-serif" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 16 }}>
        PrintReady Vectorizer (MVP)
      </h1>

      <div style={{ display: "flex", gap: 24, alignItems: "center", marginBottom: 12 }}>
        <input type="file" accept="image/*" onChange={onChoose} />
        <button onClick={onVectorize} style={btnStyle}>Vectorize</button>

        {svgMarkup && (
          <a
            ref={downloadRef}
            href={downloadHref}
            download="vectorized.svg"
            style={{ color: "#0b5bd3", textDecoration: "underline" }}
          >
            Download SVG
          </a>
        )}
      </div>

      <fieldset style={panelStyle}>
        <legend style={legendStyle}>Options</legend>

        <label style={labelStyle}>
          Max Colors:&nbsp;
          <select
            value={maxColors}
            onChange={(e) => setMaxColors(Number(e.target.value))}
          >
            {[1,2,3,4,5,6,7,8].map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>

        <label style={labelStyle}>
          <input
            type="checkbox"
            checked={primitiveSnap}
            onChange={(e) => setPrimitiveSnap(e.target.checked)}
          />
          &nbsp;Primitive snap
        </label>

        <small style={{ color: "#666" }}>
          Tip: For logos with multiple inks, try 3–6 colors. If edges look ragged,
          toggle Primitive snap.
        </small>
      </fieldset>

      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 24, marginTop: 16 }}>
        <section>
          <h3 style={{ marginBottom: 8 }}>Input Preview</h3>
          <div style={frameStyle}>
            {previewUrl ? (
              <img src={previewUrl} style={{ width: "100%", height: "auto" }} alt="preview" />
            ) : (
              <div style={emptyStyle}>No file selected</div>
            )}
          </div>
        </section>

        <section>
          <h3 style={{ marginBottom: 8 }}>Output SVG</h3>
          <div style={{ ...frameStyle, minHeight: 360 }}>
            {error && <pre style={errorStyle}>{error}</pre>}
            {svgMarkup && (
              <div
                // render the returned SVG markup
                dangerouslySetInnerHTML={{ __html: svgMarkup }}
                style={{ width: "100%", height: "auto" }}
              />
            )}
            {!error && !svgMarkup && <div style={emptyStyle}>No result yet</div>}
          </div>
        </section>
      </div>
    </main>
  );
}

const btnStyle: React.CSSProperties = {
  padding: "8px 12px",
  borderRadius: 8,
  border: "1px solid #ccc",
  background: "#111",
  color: "#fff",
  cursor: "pointer",
};

const panelStyle: React.CSSProperties = {
  display: "flex",
  gap: 16,
  alignItems: "center",
  padding: 12,
  borderRadius: 10,
  border: "1px solid #e5e5e5",
};

const legendStyle: React.CSSProperties = {
  fontWeight: 600,
  padding: "0 6px",
};

const labelStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
};

const frameStyle: React.CSSProperties = {
  border: "1px solid #e5e5e5",
  borderRadius: 10,
  padding: 10,
  background: "#fff",
  overflow: "auto",
};

const emptyStyle: React.CSSProperties = {
  color: "#777",
  fontStyle: "italic",
};

const errorStyle: React.CSSProperties = {
  color: "#b00020",
  whiteSpace: "pre-wrap",
};
