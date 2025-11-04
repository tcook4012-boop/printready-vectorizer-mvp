"use client";
import React, { useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

export default function Home() {
  const [file, setFile] = useState<File|null>(null);
  const [svg, setSvg] = useState<string|null>(null);
  const [loading, setLoading] = useState(false);
  const [maxColors, setMaxColors] = useState(8);
  const [smoothness, setSmoothness] = useState('medium');
  const [primitiveSnap, setPrimitiveSnap] = useState(true);
  const [hqRefine, setHqRefine] = useState(false);

  const onUpload = async () => {
    if (!file) return;
    setLoading(true);
    const form = new FormData();
    form.append('file', file);
    form.append('max_colors', String(maxColors));
    form.append('smoothness', smoothness);
    form.append('primitive_snap', String(primitiveSnap));
    form.append('hq_refine', String(hqRefine));
    try {
      const res = await fetch(`${API_BASE}/vectorize`, { method: 'POST', body: form });
      const text = await res.text();
      setSvg(text);
    } catch (e) {
      alert('Error: ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{maxWidth:960, margin:'40px auto', fontFamily:'system-ui'}}>
      <h1>PrintReady Vectorizer (MVP)</h1>
      <p>Upload a logo/image. This runs a first‑party tracer (no Potrace/VTracer).</p>

      <div style={{display:'flex', gap:16, alignItems:'center', margin:'12px 0'}}>
        <input type="file" accept="image/*" onChange={e=>setFile(e.target.files?.[0]||null)} />
        <label>Max Colors
          <input type="number" value={maxColors} min={2} max={32} onChange={e=>setMaxColors(parseInt(e.target.value||'8'))} style={{marginLeft:8,width:64}}/>
        </label>
        <label>Smoothness
          <select value={smoothness} onChange={e=>setSmoothness(e.target.value)} style={{marginLeft:8}}>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </label>
        <label>
          <input type="checkbox" checked={primitiveSnap} onChange={e=>setPrimitiveSnap(e.target.checked)} />
          Primitive snap
        </label>
        <label>
          <input type="checkbox" checked={hqRefine} onChange={e=>setHqRefine(e.target.checked)} />
          HQ refine (placeholder)
        </label>
        <button onClick={onUpload} disabled={!file || loading}>{loading ? 'Processing...' : 'Vectorize'}</button>
      </div>

      <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginTop:24}}>
        <div style={{border:'1px solid #ddd', padding:8}}>
          <h3>Input Preview</h3>
          {file ? <img src={URL.createObjectURL(file)} style={{maxWidth:'100%'}}/> : <div>Choose an image file.</div>}
        </div>
        <div style={{border:'1px solid #ddd', padding:8}}>
          <h3>Output SVG</h3>
          {svg ? <div dangerouslySetInnerHTML={{__html: svg}}/> : <div>No output yet.</div>}
        </div>
      </div>
    </main>
  );
}
