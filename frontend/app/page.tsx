"use client";
import React, { useState } from "react";
// ⬇️ use RELATIVE paths instead of "@/..."
import { vectorizeImage } from "../lib/api";
import { normalizeSvg } from "../lib/svg";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [maxColors, setMaxColors] = useState(4);
  const [primitiveSnap, setPrimitiveSnap] = useState(false);
  const [smoothness, setSmoothness] = useState<"low" | "medium" | "high">("medium");
  const [svg, setSvg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleVectorize = async () => {
    if (!file) {
      setError("Please upload an image");
      return;
    }
    try {
      setError(null);
      setLoading(true);

      const rawSvg = await vectorizeImage(file, {
        maxColors,
        primitiveSnap,
        smoothness,
        minPathArea: 0.0005,
      });

      const cleaned = normalizeSvg(rawSvg);
      setSvg(cleaned);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const downloadSvg = () => {
    if (!svg) return;
    const blob = new Blob([svg], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "output.svg";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main style={{ padding: 20 }}>
      <h1>PrintReady Vectorizer</h1>

      <input
        type="file"
        accept="image/*"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
      />

      <div style={{ margin: "10px 0" }}>
        <label>Max Colors (2–8): </label>
        <input
          type="number"
          min={2}
          max={8}
          value={maxColors}
          onChange={(e) => setMaxColors(Number(e.target.value))}
        />
      </div>

      <div>
        <label>Smoothness: </label>
        <select
          value={smoothness}
          onChange={(e) => setSmoothness(e.target.value as any)}
        >
          <option value="low">Low (faster, sharper)</option>
          <option value="medium">Medium</option>
          <option value="high">High (smoother curves)</option>
        </select>
      </div>

      <div>
        <label>
          <input
            type="checkbox"
            checked={primitiveSnap}
            onChange={(e) => setPrimitiveSnap(e.target.checked)}
          />
          Primitive Snap
        </label>
      </div>

      <button onClick={handleVectorize} disabled={loading}>
        {loading ? "Processing..." : "Vectorize"}
      </button>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {svg && (
        <>
          <h3>Output:</h3>
          <div
            style={{ border: "1px solid #999", width: "500px", height: "500px" }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
          <button onClick={downloadSvg}>Download SVG</button>
        </>
      )}
    </main>
  );
}
