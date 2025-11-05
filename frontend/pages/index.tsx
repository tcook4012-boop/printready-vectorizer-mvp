import React, { useMemo, useState } from "react";

/**
 * Debug-friendly Vectorizer frontend.
 * - Shows file metadata (name/type/size)
 * - Optionally converts to PNG client-side before upload
 * - Prints raw response text & status
 * - Sends multipart/form-data with exact FastAPI field names
 */

type VectorizeOk = { svg: string };
type VectorizeErr = { detail?: unknown };

const DEFAULT_API_BASE =
  (process.env.NEXT_PUBLIC_API_BASE || "").trim() ||
  "https://printready-vectorizer-api.onrender.com";

export default function Home() {
  // UI state
  const [file, setFile] = useState<File | null>(null);
  const [maxColors, setMaxColors] = useState<number>(8);
  const [smoothness, setSmoothness] = useState<"low" | "medium" | "high">(
    "medium"
  );
  const [primitiveSnap, setPrimitiveSnap] = useState<boolean>(true);
  const [sendAsPng, setSendAsPng] = useState<boolean>(true); // NEW: try PNG conversion by default
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [svg, setSvg] = useState<string>("");

  // Debug/state: raw response & status
  const [respStatus, setRespStatus] = useState<number | null>(null);
  const [rawResponse, setRawResponse] = useState<string>("");

  // Allow overriding API quickly if needed
  const [apiBase, setApiBase] = useState<string>(DEFAULT_API_BASE);
  const apiUrl = `${apiBase.replace(/\/+$/, "")}/vectorize`;

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : ""), [file]);

  const onChooseFile: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.currentTarget.files?.[0] ?? null;
    setFile(f);
    setSvg("");
    setError(null);
    setRawResponse("");
    setRespStatus(null);
  };

  const makePngBlob = async (sourceFile: File): Promise<Blob> => {
    // Draw the image to a canvas and export as PNG
    const bitmap = await createImageBitmap(sourceFile);
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas 2D context not available.");
    ctx.drawImage(bitmap, 0, 0);
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob((b) => resolve(b), "image/png")
    );
    if (!blob) throw new Error("Failed to convert image to PNG.");
    return blob;
  };

  const vectorize = async () => {
    try {
      setBusy(true);
      setError(null);
      setSvg("");
      setRawResponse("");
      setRespStatus(null);

      if (!file) {
        setError("Please choose an image first.");
        return;
      }

      let uploadFile: File | Blob = file;
      let uploadName = file.name;
      let uploadType = file.type;

      // Optional: convert to PNG first (server will definitely accept PNG)
      if (sendAsPng) {
        const pngBlob = await makePngBlob(file);
        uploadFile = pngBlob;
        uploadName = file.name.replace(/\.\w+$/, "") + ".png";
        uploadType = "image/png";
      }

      // Build multipart form
      const form = new FormData();
      form.append("file", uploadFile, uploadName); // exact field name expected by FastAPI
      form.append("max_colors", String(maxColors));
      form.append("smoothness", smoothness);
      form.append("primitive_snap", primitiveSnap ? "true" : "false");

      const res = await fetch(apiUrl, {
        method: "POST",
        body: form,
      });

      setRespStatus(res.status);
      const text = await res.text();
      setRawResponse(text);

      // Try to parse JSON
      let json: VectorizeOk | VectorizeErr;
      try {
        json = JSON.parse(text);
      } catch {
        throw new Error(`Non-JSON response from API: ${text.slice(0, 300)}…`);
      }

      if (!res.ok) {
        const msg =
          typeof (json as any)?.detail === "string"
            ? (json as any).detail
            : JSON.stringify((json as any)?.detail ?? json);
        throw new Error(`API error (${res.status}): ${msg}`);
      }

      if ("svg" in json && typeof json.svg === "string") {
        setSvg(json.svg);
        if (!json.svg.trim()) {
          setError("API returned an empty SVG string.");
        }
      } else {
        setError("Unexpected API payload shape.");
      }
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main style={{ padding: 24, maxWidth: 1200, margin: "0 auto" }}>
      <h1 style={{ marginBottom: 8 }}>PrintReady Vectorizer (MVP)</h1>
      <p style={{ marginTop: 0, color: "#666" }}>
        Upload a logo/image. This runs a first-party tracer (no Potrace/VTracer).
      </p>

      {/* API URL control */}
      <div
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          marginBottom: 12,
          flexWrap: "wrap",
        }}
      >
        <label style={{ fontSize: 12, color: "#666" }}>API base:</label>
        <input
          style={{ width: 520 }}
          value={apiBase}
          onChange={(e) => setApiBase(e.target.value)}
        />
        <span style={{ fontSize: 12, color: "#666" }}>
          POST <code>{apiUrl}</code>
        </span>
      </div>

      <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
        <div>
          <input type="file" accept="image/*" onChange={onChooseFile} />
          <div style={{ fontSize: 12, color: "#888" }}>
            {file ? `${file.name} (${file.type || "unknown"}; ${file.size} bytes)` : "No file selected"}
          </div>
        </div>

        <div>
          <div>Max Colors</div>
          <input
            type="number"
            min={2}
            max={32}
            value={maxColors}
            onChange={(e) => setMaxColors(Number(e.target.value) || 8)}
            style={{ width: 80 }}
          />
        </div>

        <div>
          <div>Smoothness</div>
          <select
            value={smoothness}
            onChange={(e) => setSmoothness(e.target.value as any)}
          >
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </div>

        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={primitiveSnap}
            onChange={(e) => setPrimitiveSnap(e.target.checked)}
          />
          Primitive snap
        </label>

        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={sendAsPng}
            onChange={(e) => setSendAsPng(e.target.checked)}
          />
          Send as PNG (browser converts)
        </label>

        <button
          onClick={vectorize}
          disabled={busy}
          style={{ padding: "8px 14px", fontWeight: 600 }}
        >
          {busy ? "Processing..." : "Vectorize"}
        </button>
      </div>

      {/* Two-column layout */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginTop: 24 }}>
        <section>
          <h3>Input Preview</h3>
          <div
            style={{
              minHeight: 300,
              border: "1px solid #ddd",
              borderRadius: 8,
              padding: 8,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "#fafafa",
            }}
          >
            {previewUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={previewUrl}
                alt="preview"
                style={{ maxWidth: "100%", maxHeight: 500 }}
              />
            ) : (
              <div style={{ color: "#aaa" }}>No image selected</div>
            )}
          </div>
        </section>

        <section>
          <h3>Output SVG</h3>
          <div
            style={{
              minHeight: 300,
              border: "1px solid #ddd",
              borderRadius: 8,
              padding: 8,
              background: "#fafafa",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
              fontSize: 12,
            }}
          >
            {error && (
              <div style={{ color: "#c00", marginBottom: 8 }}>
                Error: {error}
              </div>
            )}
            {!error && !svg && <div style={{ color: "#aaa" }}>No output yet.</div>}
            {!error && svg && (
              <>
                <div style={{ marginBottom: 8, color: "#555" }}>
                  First 200 chars:
                </div>
                <div>{svg.slice(0, 200)}{svg.length > 200 ? "…" : ""}</div>
                <div style={{ marginTop: 12 }}>
                  <DownloadButton svg={svg} />
                </div>
              </>
            )}
          </div>

          {/* Debug panel */}
          <div style={{ marginTop: 16, borderTop: "1px solid #eee", paddingTop: 12 }}>
            <details open>
              <summary>Debug</summary>
              <div style={{ fontSize: 12, color: "#444", marginTop: 8 }}>
                <div>API URL: <code>{apiUrl}</code></div>
                <div>Selected file: <code>{file ? `${file.name} | ${file.type} | ${file.size} bytes` : "—"}</code></div>
                <div>Sent as PNG: <code>{sendAsPng ? "yes" : "no"}</code></div>
                <div>Response status: <code>{respStatus ?? "—"}</code></div>
                <div>Raw response (first 400 chars):</div>
                <pre style={{ whiteSpace: "pre-wrap", background: "#f7f7f7", padding: 8, borderRadius: 6 }}>
                  {rawResponse ? rawResponse.slice(0, 400) + (rawResponse.length > 400 ? "…" : "") : "—"}
                </pre>
              </div>
            </details>
          </div>
        </section>
      </div>
    </main>
  );
}

function DownloadButton({ svg }: { svg: string }) {
  const handleDownload = () => {
    const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "vectorized.svg";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };
  return (
    <button onClick={handleDownload} style={{ padding: "6px 12px" }}>
      Download SVG
    </button>
  );
}
