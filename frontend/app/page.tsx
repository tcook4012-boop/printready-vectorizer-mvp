// frontend/app/page.tsx
"use client";
import React, { useMemo, useRef, useState } from "react";
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
  const [raw, setRaw] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useRawSvg, setUseRawSvg] = useState(false); // NEW: bypass normalizer (debug)

  const [zoom, setZoom] = useState(0.75);
  const viewportRef = useRef<HTMLDivElement>(null);

  const handleVectorize = async () => {
    if (!file) {
      setError("Please upload an image");
      return;
    }
    try {
      setError(null);
      setSvg(null);
      setRaw(null);
      setLoading(true);

      const rawSvg = await vectorizeImage(file, {
        maxColors,
        primitiveSnap,
        smoothness,
        minPathArea,
        order,
      } as any);

      const rawStr = typeof rawSvg === "string" ? rawSvg : JSON.stringify(rawSvg);
      setRaw(rawStr);

      // If user toggles "Bypass normalizer", try to render raw unmodified.
      const candidate = useRawSvg ? rawStr : normalizeSvg(String(rawStr || ""));
      if (!candidate || !/<svg\b/i.test(candidate)) {
        setError(
          "API returned data but it wasn't a usable <svg>. First 300 chars:\n" +
          String(rawStr).slice(0, 300)
        );
        return;
      }
      setSvg(candidate);
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

  const scaledStyle = useMemo(
    () => ({
      transform: `scale(${zoom})`,
      transformOrigin: "top left",
      display: "inline-block",
    }),
    [zoom]
  );

  const fitIsh = () => setZoom(0.8);

  return (
    <main style={{ padding: 20, maxWidth: 980, margin: "0 auto" }}>
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
          {" "}Primitive Snap
        </label>
      </div>

      <div style={{ marginTop: 8 }}>
        <label>
          <input
            type="checkbox"
            checked={useRawSvg}
            onChange={(e) => setUseRawSvg(e.target.checked)}
          />
          {" "}Bypass normalizer (debug)
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

      {error && (
        <pre style={{ color: "red", whiteSpace: "pre-wrap", marginTop: 10 }}>
          {error}
        </pre>
      )}

      <div style={{ marginTop: 18, display: "flex", alignItems: "center", gap: 8 }}>
        <strong>Output:</strong>
        <span>Zoom:&nbsp;</span>
        <input
          type="range"
          min={0.25}
          max={4}
          step={0.05}
          value={zoom}
          onChange={(e) => setZoom(Number(e.target.value))}
          style={{ width: 200 }}
        />
        <button onClick={() => setZoom(0.75)}>75%</button>
        <button onClick={() => setZoom(1)}>100%</button>
        <button onClick={() => setZoom(2)}>200%</button>
        <button onClick={fitIsh}>Fit-ish</button>
      </div>

      <div
        ref={viewportRef}
        style={{
          border: "1px solid #999",
          width: "100%",
          height: 520,
          overflow: "auto",
          background: "#fff",
          marginTop: 8,
          position: "relative",
        }}
      >
        {svg ? (
          <div
            style={scaledStyle}
            // eslint-disable-next-line react/no-danger
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        ) : (
          <div style={{ color: "#888", padding: 12 }}>
            {loading ? "Rendering..." : "No output yet."}
          </div>
        )}
      </div>

      {svg && (
        <button onClick={downloadSvg} style={{ marginTop: 10 }}>
          Download SVG
        </button>
      )}

      {raw && !svg && (
        <details style={{ marginTop: 10 }}>
          <summary>Debug: Raw API response (first 400 chars)</summary>
          <pre style={{ whiteSpace: "pre-wrap" }}>{String(raw).slice(0, 400)}</pre>
        </details>
      )}
    </main>
  );
}
