// pages/index.tsx
import { useState } from "react";
import { vectorizeImage, pingHealth } from "../lib/api";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [svg, setSvg] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const doVectorize = async () => {
    try {
      if (!file) throw new Error("Choose a file first.");
      setBusy(true);
      setMsg("Uploading…");
      const res = await vectorizeImage(file);
      setSvg(res.svg);
      setMsg("Done.");
    } catch (e: any) {
      setMsg(e?.message || "Failed");
      alert(e?.message || "Failed");
    } finally {
      setBusy(false);
    }
  };

  const checkHealth = async () => {
    try {
      const t = await pingHealth();
      alert(`Backend /health: ${t}`);
    } catch (e: any) {
      alert(e?.message || "Health check failed");
    }
  };

  return (
    <main style={{ maxWidth: 900, margin: "40px auto", fontFamily: "system-ui" }}>
      <h1>PrintReady Vectorizer</h1>
      <p>
        Backend: <code>{process.env.NEXT_PUBLIC_API_URL || "(default)"}</code>
      </p>

      <div style={{ margin: "12px 0" }}>
        <input
          type="file"
          accept="image/*"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        <button onClick={doVectorize} disabled={!file || busy} style={{ marginLeft: 8 }}>
          {busy ? "Working…" : "Vectorize"}
        </button>
        <button onClick={checkHealth} style={{ marginLeft: 8 }}>
          Check /health
        </button>
      </div>

      <div style={{ margin: "8px 0", color: "#555" }}>{msg}</div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <h3>Input preview</h3>
          {file ? (
            <img
              src={URL.createObjectURL(file)}
              alt="preview"
              style={{ maxWidth: "100%", border: "1px solid #ddd" }}
            />
          ) : (
            <div style={{ padding: 20, border: "1px dashed #ccc" }}>No file chosen.</div>
          )}
        </div>
        <div>
          <h3>Output SVG</h3>
          {svg ? (
            <div
              style={{ border: "1px solid #ddd", padding: 10, minHeight: 200 }}
              dangerouslySetInnerHTML={{ __html: svg }}
            />
          ) : (
            <div style={{ padding: 20, border: "1px dashed #ccc" }}>No output yet.</div>
          )}
        </div>
      </div>
    </main>
  );
}
