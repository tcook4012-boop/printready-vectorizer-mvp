import React, { useRef, useState } from "react";

const DEFAULT_MAX_COLORS = 8;

export default function Home() {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [maxColors, setMaxColors] = useState<number>(DEFAULT_MAX_COLORS);
  const [smoothness, setSmoothness] = useState<"low"|"medium"|"high">("medium");
  const [primitiveSnap, setPrimitiveSnap] = useState<boolean>(true);
  const [svg, setSvg] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE; // e.g. https://printready-vectorizer-api.onrender.com

  async function onVectorize() {
    setError("");
    setSvg("");

    const f = fileRef.current?.files?.[0];
    if (!f) {
      setError("Please choose a file first.");
      return;
    }
    if (!API_BASE) {
      setError("NEXT_PUBLIC_API_BASE is not set. In Vercel, go to Settings → Environment Variables and set it to your Render API base URL.");
      return;
    }

    setBusy(true);
    try {
      const form = new FormData();
      // IMPORTANT: field names must match the FastAPI endpoint
      form.append("file", f, f.name);
      form.append("max_colors", String(maxColors));
      form.append("smoothness", smoothness);
      form.append("primitive_snap", String(primitiveSnap));

      const res = await fetch(`${API_BASE}/vectorize`, {
        method: "POST",
        body: form,
      });

      const text = await res.text();

      // Try JSON first; fall back to raw string (helps debug)
      let data: any = null;
      try { data = JSON.parse(text); } catch { /* ignore */ }

      if (!res.ok) {
        setError(data?.detail ? String(data.detail) : `HTTP ${res.status}: ${text}`);
        return;
      }

      const svgText: string = data?.svg ?? "";
      setSvg(svgText);

      // Quick hint if backend returns empty svg
      if (!svgText || svgText.replace(/\s/g, "").length < 100) {
        setError("Backend returned an empty/very short SVG. Check the Render logs for /vectorize.");
      }
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 1100, margin: "40px auto", fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial" }}>
      <h1 style={{ fontSize: 36, marginBottom: 8 }}>PrintReady Vectorizer (MVP)</h1>
      <p style={{ color: "#333", marginBottom: 24 }}>
        Upload a logo/image. This runs a first-party tracer (no Potrace/VTracer).
      </p>

      <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap", marginBottom: 16 }}>
        <input ref={fileRef} type="file" accept="image/*" />
        <div>
          <div style={{ fontSize: 12, opacity: 0.7 }}>Max Colors</div>
          <input
            type="number"
            min={2}
            max={32}
            value={maxColors}
            onChange={(e) => setMaxColors(Number(e.target.value || DEFAULT_MAX_COLORS))}
            style={{ width: 72 }}
          />
        </div>
        <div>
          <div style={{ fontSize: 12, opacity: 0.7 }}>Smoothness</div>
          <select value={smoothness} onChange={(e) => setSmoothness(e.target.value as any)}>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={primitiveSnap} onChange={(e) => setPrimitiveSnap(e.target.checked)} />
          Primitive snap
        </label>
        <button
          onClick={onVectorize}
          disabled={busy}
          style={{
            padding: "8px 16px",
            background: "#111",
            color: "#fff",
            borderRadius: 6,
            border: "none",
            cursor: "pointer",
          }}
        >
          {busy ? "Processing…" : "Vectorize"}
        </button>
      </div>

      {!!API_BASE && (
        <div style={{ fontSize: 12, opacity: 0.6, marginBottom: 16 }}>
          Using API: <code>{API_BASE}/vectorize</code>
        </div>
      )}

      {error && (
        <div style={{ background: "#fff3cd", border: "1px solid #ffeeba", color: "#856404", padding: 12, borderRadius: 6, marginBottom: 12 }}>
          {error}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 16 }}>
          <h3>Input Preview</h3>
          <div style={{ border: "1px solid #ddd", minHeight: 360, display: "grid", placeItems: "center" }}>
            {/* Simple preview via object URL */}
            {fileRef.current?.files?.[0] ? (
              <img
                alt="preview"
                src={URL.createObjectURL(fileRef.current.files[0])}
                style={{ maxWidth: "100%", maxHeight: 480 }}
                onLoad={(e) => URL.revokeObjectURL((e.target as HTMLImageElement).src)}
              />
            ) : (
              <div style={{ opacity: 0.5 }}>No file chosen</div>
            )}
          </div>
        </div>

        <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 16 }}>
          <h3>Output SVG</h3>
          <div style={{ minHeight: 360, border: "1px solid #ddd", padding: 12, overflow: "auto" }}>
            {svg ? (
              <div
                // Render the SVG string
                dangerouslySetInnerHTML={{ __html: svg }}
              />
            ) : (
              <pre style={{ margin: 0, opacity: 0.6 }}>{"(empty)"}</pre>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
