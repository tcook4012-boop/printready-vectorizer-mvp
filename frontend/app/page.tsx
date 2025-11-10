"use client";
import React, { useState } from "react";
import { vectorizeImage } from "../lib/api";
import { normalizeSvg } from "../lib/svg";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [maxColors, setMaxColors] = useState(4);
  const [primitiveSnap, setPrimitiveSnap] = useState(false);
  const [smoothness, setSmoothness] = useState<"low" | "medium" | "high">("medium");
  const [minPathArea, setMinPathArea] = useState(0.0005);
  const [order, setOrder] = useState<"light_to_dark" | "dark_to_light">("light_to_dark");
  const [showAdvanced, setShowAdvanced] = useState(false);

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
      setSvg(null);
      setLoading(true);

      const rawSvg = await vectorizeImage(file, {
        maxColors,
        primitiveSnap,
        smoothness,
        minPathArea,
        order,
      } as any);

      const cleaned = normalizeSvg(rawSvg);

      // If backend returns non-SVG, surface it to UI
      if (!cleaned || !cleaned.toLowerCase().includes("<svg")) {
        console.warn("Non-SVG API response:", rawSvg?.slice(0, 500));
        setError(
          "API did not return embeddable SVG. First 300 chars:\n" +
            String(rawSvg).slice(0, 300)
        );
        return;
      }

      setSvg(cleaned);
    } catch (e: any) {
      const msg = String(e?.message || e);
      setError(
        msg.includes("Failed to fetch")
          ? "Could not reach API — check NEXT_PUBLIC_API_BASE."
          : msg
      );
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
    <main style={{ padding: 20, maxWidth: 900 }}>
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

      <div style={{ marginTop: 10 }}>
        <button onClick={() => setShowAdvanced(!showAdvanced)}>
          {showAdvanced ? "Hide Advanced" : "Show Advanced"}
        </button>
      </div>

      {showAdvanced && (
        <div style={{ border: "1px solid #ddd", padding: 10, marginTop: 8 }}>
          <div>
            <label>Min Path Area (fraction of pixels): </label>
            <input
              type="number"
              step={0.0001}
              min={0}
              value={minPathArea}
              onChange={(e) => setMinPathArea(Number(e.target.value))}
            />
            <span style={{ marginLeft: 8, color: "#666" }}>
              (try 0.0002 – 0.001 to remove specks)
            </span>
          </div>

          <div style={{ marginTop: 8 }}>
            <label>Layer Order: </label>
            <select value={order} onChange={(e) => setOrder(e.target.value as any)}>
              <option value="light_to_dark">Light → Dark</option>
              <option value="dark_to_light">Dark → Light</option>
            </select>
          </div>
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        <button onClick={handleVectorize} disabled={loading}>
          {loading ? "Processing..." : "Vectorize"}
        </button>
      </div>

      {/* Show API errors */}
      {error && (
        <pre style={{ color: "red", whiteSpace: "pre-wrap", marginTop: 10 }}>
          {error}
        </pre>
      )}

      {/* SVG Output */}
      {svg && (
        <>
          <h3>Output:</h3>
          <div
            style={{
              border: "1px solid #999",
              width: 600,
              height: 500,
              overflow: "hidden",
              background: "#fff",
            }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
          <button onClick={downloadSvg} style={{ marginTop: 8 }}>
            Download SVG
          </button>
        </>
      )}
    </main>
  );
}
