"use client";
import React, { useMemo, useState } from "react";
import { vectorizeImage } from "../lib/api";
import { normalizeSvg } from "../lib/svg";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [maxColors, setMaxColors] = useState(4);
  const [primitiveSnap, setPrimitiveSnap] = useState(false);
  const [smoothness, setSmoothness] = useState<"low" | "medium" | "high">(
    "medium"
  );
  const [minPathArea, setMinPathArea] = useState(0.0005);
  const [order, setOrder] = useState<"light_to_dark" | "dark_to_light">(
    "light_to_dark"
  );
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [svg, setSvg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Preview helpers
  const [zoom, setZoom] = useState<number>(100); // %
  const zoomScale = useMemo(() => Math.max(0.25, Math.min(2, zoom / 100)), [zoom]);

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

      if (!cleaned || !cleaned.toLowerCase().includes("<svg")) {
        console.warn("Non-SVG API response:", String(rawSvg)?.slice(0, 500));
        setError(
          "API did not return embeddable SVG. First 300 chars:\n" +
            String(rawSvg).slice(0, 300)
        );
        return;
      }

      setSvg(cleaned);
      // try to start preview fit-ish
      setZoom(100);
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
    <main style={{ padding: 20, maxWidth: 1100, margin: "0 auto" }}>
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
            <select
              value={order}
              onChange={(e) => setOrder(e.target.value as any)}
            >
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
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 18 }}>
            <h3 style={{ margin: 0 }}>Output:</h3>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              Zoom:
              <input
                type="range"
                min={25}
                max={200}
                step={5}
                value={zoom}
                onChange={(e) => setZoom(Number(e.target.value))}
              />
              <span style={{ width: 48, textAlign: "right" }}>{zoom}%</span>
            </label>
            <button onClick={() => setZoom(100)}>100%</button>
            <button onClick={() => setZoom(200)}>200%</button>
            <button onClick={() => setZoom(75)}>Fit-ish</button>
          </div>

          {/* Scrollable preview area */}
          <div
            style={{
              border: "1px solid #999",
              maxWidth: "100%",
              height: "70vh",
              overflow: "auto",             // <-- scrollbars appear as needed
              background: "#fff",
              marginTop: 8,
              padding: 12,
            }}
          >
            {/* scale the SVG inside, but keep natural size so scrollbars work */}
            <div
              style={{
                transform: `scale(${zoomScale})`,
                transformOrigin: "top left",
                width: "max-content",       // allows scroll of scaled content
                height: "max-content",
              }}
              // NOTE: we purposely render the raw SVG markup
              dangerouslySetInnerHTML={{ __html: svg }}
            />
          </div>

          <button onClick={downloadSvg} style={{ marginTop: 10 }}>
            Download SVG
          </button>
        </>
      )}
    </main>
  );
}
