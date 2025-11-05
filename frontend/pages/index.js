import { useState } from "react";

export default function Home() {
  const [preview, setPreview] = useState(null);
  const [svgOutput, setSvgOutput] = useState("No output yet.");

  // ✅ Change this to your Render API
  const API_BASE = "https://printready-vectorizer-api.onrender.com";

  const handleFile = (e) => {
    const file = e.target.files[0];
    if (file) setPreview(URL.createObjectURL(file));
  };

  const vectorize = async () => {
    const fileInput = document.getElementById("file");
    const file = fileInput.files[0];
    if (!file) return alert("Please choose a file first.");

    setSvgOutput("Processing...");

    const form = new FormData();
    form.append("file", file);
    form.append("max_colors", "8");
    form.append("smoothness", "medium");
    form.append("primitive_snap", "true");

    try {
      const res = await fetch(`${API_BASE}/vectorize`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
      }

      const data = await res.json();

      if (typeof data.svg === "string" && data.svg.startsWith("<svg")) {
        setSvgOutput(data.svg); // ✅ display inline
      } else {
        setSvgOutput(JSON.stringify(data, null, 2)); // fallback
      }
    } catch (err) {
      setSvgOutput("Error: " + err.message);
    }
  };

  return (
    <div style={{ padding: 30, fontFamily: "Arial" }}>
      <h1>PrintReady Vectorizer (MVP)</h1>
      <p>Upload an image to convert it into SVG.</p>

      <input id="file" type="file" onChange={handleFile} />
      <button onClick={vectorize} style={{ marginLeft: 10 }}>
        Vectorize
      </button>

      <div style={{ display: "flex", marginTop: 20, gap: 30 }}>
        <div style={{ width: "45%" }}>
          <h3>Input Preview</h3>
          {preview && (
            <img
              src={preview}
              alt="preview"
              style={{ maxWidth: "100%", border: "1px solid #ddd" }}
            />
          )}
        </div>

        <div style={{ width: "45%" }}>
          <h3>Output SVG</h3>
          <div
            style={{
              border: "1px solid #ddd",
              minHeight: 300,
              padding: 10,
              background: "#fafafa",
            }}
            dangerouslySetInnerHTML={{ __html: svgOutput }}
          />
        </div>
      </div>
    </div>
  );
}
