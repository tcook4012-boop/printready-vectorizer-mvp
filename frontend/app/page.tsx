// frontend/app/page.tsx
"use client";

import { useRef, useState } from "react";
import { normalizeSvg, vectorizeRequest } from "../lib/api";

export default function Home() {
  const fileRef = useRef<HTMLInputElement>(null);
  const outRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadHref, setDownloadHref] = useState<string>("");

  async function onVectorize() {
    setError(null);
    setDownloadHref("");
    if (!fileRef.current?.files?.[0]) {
      setError("Please choose an image file first.");
      return;
    }
    const file = fileRef.current.files[0];

    setBusy(true);
    try {
      const svgRaw = await vectorizeRequest(file, {
        maxColors: 8,
        smoothness: "medium",
        primitiveSnap: false, // can toggle later in UI
      });

      const svg = normalizeSvg(svgRaw);

      // Render
      if (outRef.current) {
        outRef.current.innerHTML = ""; // clear
        outRef.current.insertAdjacentHTML("afterbegin", svg);
      }

      // Enable download
      const href =
        "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
      setDownloadHref(href);
    } catch (e: any) {
      setError(e?.message || String(e));
      if (outRef.current) outRef.current.textContent = "";
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1>PrintReady Vectorizer (MVP)</h1>

      <div style={{ margin: "12px 0" }}>
        <input ref={fileRef} type="file" accept="image/*" />
        <button onClick={onVectorize} disabled={busy} style={{ marginLeft: 12 }}>
          {busy ? "Processing…" : "Vectorize"}
        </button>
        {downloadHref && (
          <a
            href={downloadHref}
            download="output.svg"
            style={{ marginLeft: 12 }}
          >
            Download SVG
          </a>
        )}
      </div>

      {error && (
        <div style={{ color: "crimson", margin: "8px 0" }}>Error: {error}</div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <section>
          <h3>Input Preview</h3>
          <div
            style={{
              height: 320,
              border: "1px solid #ddd",
              display: "grid",
              placeItems: "center",
              padding: 12,
            }}
          >
            {fileRef.current?.files?.[0] ? (
              <img
                alt="preview"
                src={URL.createObjectURL(fileRef.current.files[0])}
                style={{ maxWidth: "100%", maxHeight: "100%" }}
                onLoad={(e) =>
                  URL.revokeObjectURL((e.currentTarget as HTMLImageElement).src)
                }
              />
            ) : (
              <small>No file selected.</small>
            )}
          </div>
        </section>

        <section>
          <h3>Output SVG</h3>
          <div
            ref={outRef}
            style={{
              height: 320,
              border: "1px solid #ddd",
              padding: 12,
              overflow: "auto",
              background: "#fff",
            }}
          />
        </section>
      </div>
    </main>
  );
}
