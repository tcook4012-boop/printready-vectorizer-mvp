"use client";

import { useState } from "react";

export default function Page() {
  const [preview, setPreview] = useState<string | null>(null);
  const [svgOutput, setSvgOutput] = useState<string>("No output yet.");

  // ✅ Your Render backend
  const API_BASE = "https://printready-vectorizer-api.onrender.com";

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setPreview(URL.createObjectURL(file));
  };

  const vectorize = async () => {
    const input = document.getElementById("file") as HTMLInputElement;
    const file = input.files?.[0];

    if (!file) {
      alert("Please choose an image first!");
      return;
    }

    setSvgOutput("Processing...");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("max_colors", "8");
    formData.append("smoothness", "medium");
    formData.append("primitive_snap", "true");

    try {
      const res = await fetch(`${API_BASE}/vectorize`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(`HTTP ${res.status}: ${err}`);
      }

      const data = await res.json();

      // ✅ backend returns inline SVG text
      if (data.svg && typeof data.svg === "string" && data.svg.startsWith("<svg")) {
        setSvgOutput(data.svg);
      } else {
        setSvgOutput("Unexpected response: " + JSON.stringify(data));
      }
    } catch (error: any) {
      setSvgOutput("Error: " + error.message);
    }
  };

  return (
    <div style={{ fontFamily: "Arial", padding: "30px" }}>
      <h1>PrintReady Vectorizer (MVP)</h1>
      <p>Upload an image and convert it into SVG.</p>

      <input id="file" type="file" accept="image/*" onChange={handleFile} />
      <button
        onClick={vectorize}
        style={{ marginLeft: 12, padding: "6px 12px", cursor: "pointer" }}
      >
        Vectorize
      </button>

      <div style={{ display: "flex", marginTop: 25, gap: 30 }}>
        <div style={{ width: "45%" }}>
          <h3>Input Preview</h3>
          {preview ? (
            <img
              src={preview}
              alt="preview"
              style={{ maxWidth: "100%", border: "1px solid #ddd" }}
            />
          ) : (
            <span>No file selected</span>
          )}
        </div>

        <div style={{ width: "45%" }}>
          <h3>Output SVG</h3>
          <div
            style={{
              border: "1px solid #ddd",
              minHeight: "300px",
              padding: "10px",
              background: "#fafafa",
              overflow: "auto",
            }}
            dangerouslySetInnerHTML={{ __html: svgOutput }}
          />
        </div>
      </div>
    </div>
  );
}
