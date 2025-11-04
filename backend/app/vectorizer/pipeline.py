import subprocess
import tempfile
import os
from typing import Literal
from PIL import Image
from io import BytesIO

Smooth = Literal["low", "medium", "high"]

def _ensure_png_from_bytes(data: bytes) -> bytes:
    """Load user bytes with Pillow and normalize to 8-bit grayscale PNG."""
    with Image.open(BytesIO(data)) as im:
        im = im.convert("L")
        buf = BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

def _run_potrace(png_bytes: bytes) -> str:
    """
    Call potrace to produce SVG and return the SVG text.
    Flags kept minimal for widest compatibility.
    """
    with tempfile.TemporaryDirectory() as td:
        png_path = os.path.join(td, "in.png")
        svg_path = os.path.join(td, "out.svg")

        with open(png_path, "wb") as f:
            f.write(png_bytes)

        # Basic, stable flags. (Avoid fancy switches that broke earlier.)
        cmd = ["potrace", "-s", "-o", svg_path, png_path]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            # Bubble up a readable error for FastAPI to show as 500
            raise RuntimeError(
                f"potrace failed (exit {e.returncode}): {e.stderr.decode(errors='ignore')}"
            )

        with open(svg_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

def vectorize_image(
    data: bytes,
    max_colors: int = 8,
    smoothness: Smooth = "medium",
    primitive_snap: bool = True,
) -> str:
    """
    Current MVP: single-pass bitmap trace via potrace.
    Returns raw SVG text (NOT a tmp path).
    """
    # (max_colors, smoothness, primitive_snap) are accepted for future use;
    # for now we produce a stable single-color trace to unblock the product.
    png_bytes = _ensure_png_from_bytes(data)
    svg_text = _run_potrace(png_bytes)
    return svg_text
