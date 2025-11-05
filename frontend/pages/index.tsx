import React, { useMemo, useState } from "react";

/**
 * PrintReady Vectorizer (MVP)
 * Frontend: Next.js Pages Router
 * Posts a multipart/form-data payload that matches the FastAPI backend.
 *
 * Expected backend fields:
 *   - file                  : image file
 *   - max_colors            : number/string
 *   - smoothness            : "low" | "medium" | "high"
 *   - primitive_snap        : "true" | "false"
 */

type VectorizeResponse =
  | { svg: string }                // success
  | { detail: unknown }            // FastAPI validation/HTTPException

const DEFAULT_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.trim() ||
  "https://printready-vectorizer-api.onrender.com";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [maxColors, setMaxColors] = useState<number>(8);
  const [smoothness, setSmoothness] = useState<"low" | "medium" | "high">(
    "medium"
  );
  const [primitiveSnap, setPrimitiveSnap] = useState<boolean>(true);
  const [hqRefine, setHqRefine] = useState<boolean>(false); // placeholder, not sent to API

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [svg, setSvg] = useState<string>("");

  const apiBase = useMemo(() => DEFAULT_API_BASE, []);
  const apiUrl = `${apiBase.replace(/\/+$/, "")}/vectorize`;

  const onChooseFile: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.currentTarget.files?.[0] ?? null;
    setFile(f);
    setSvg("");
    setError(null);
  };

  const vectorize = async () => {
    try {
      setBusy(true);
      setError(null);
      setSvg("");

      if (!file) {
        setError("Please choose an image first.");
        return;
      }

      const form = new FormData();
      // IMPORTANT: field names must match FastAPI param names:
      form.append("file", file, file.name);
      form.append("max_colors", String(maxColors));
      form.append("smoothness", smoothness);
      form.append("primitive_snap", primitiveSnap ? "true" : "false");

      const res = await fetch(apiUrl, {
        method: "POST",
        body: form,
        // Don't set Content-Type; browser will set correct multipart boundary
      });

      const text = await res.text(); // for easier debugging
      let json: VectorizeResponse;
      try {
        json = JSON.parse(text);
      } catch {
        throw new Error(`Non-JSON response from API: ${text.slice(0, 200)}…`);
      }

      if (!res.ok) {
        // FastAPI may return {"detail": ...}
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

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : ""), [file]);

  return (
    <main style={{ padding: 24, maxWidth: 1200, margin: "0 auto" }}>
      <h1 style={{ marginBottom: 8 }}>PrintReady Vectorizer (MVP)</h1>

      <p style={{ marginTop: 0, color: "#666" }}>
        Upload a logo/image. This runs a first-party tracer (no Potrace/VTracer).
      </p>

      <div style={{ margin: "8px 0 16px", fontSize: 12, color: "#666" }}>
        Using API: <code>{apiUrl}</code>
      </div>

      <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
        <div>
          <input type="file" accept="image/*" onChange={onChooseFile} />
          <div style={{ fontSize: 12, color: "#888" }}>
            {file ? file.name : "No file selected"}
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

        <label style={{ display: "flex", gap: 8, alignItems: "center", opacity: 0.5 }}>
          <input
            type="checkbox"
            checked={hqRefine}
            onChange={(e) => setHqRefine(e.target.checked)}
            disabled
          />
          HQ refine (placeholder)
        </label>

        <button
          onClick={vectorize}
          disabled={busy}
          style={{ padding: "8px 14px", fontWeight: 600 }}
        >
          {busy ? "Processing..." : "Vectorize"}
        </button>
      </div>

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
                <div style={{ marginTop: 12, borderTop: "1px solid #eee", paddingTop: 8 }}>
                  <details>
                    <summary>Full SVG</summary>
                    <pre style={{ whiteSpace: "pre-wrap" }}>{svg}</pre>
                  </details>
                </div>
              </>
            )}
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
