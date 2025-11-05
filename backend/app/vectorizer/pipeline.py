import io
import os
import tempfile
import subprocess
from PIL import Image


def _png_bytes_to_bmp_bytes(png_bytes: bytes) -> bytes:
    """Convert any uploaded raster to BMP bytes (format potrace accepts)."""
    img = Image.open(io.BytesIO(png_bytes))
    # Convert to grayscale for a cleaner trace (potrace is mono)
    if img.mode not in ("L", "1"):
        img = img.convert("L")
    out_buf = io.BytesIO()
    img.save(out_buf, format="BMP")
    return out_buf.getvalue()


def _run_potrace_on_bmp(bmp_bytes: bytes) -> str:
    """
    Write BMP to /tmp, run potrace to SVG, and return SVG text.
    Raises RuntimeError with stderr if potrace fails.
    """
    with tempfile.TemporaryDirectory() as td:
        in_path = os.path.join(td, "in.bmp")
        out_path = os.path.join(td, "out.svg")

        with open(in_path, "wb") as f:
            f.write(bmp_bytes)

        # Basic potrace command: BMP -> SVG
        cmd = ["potrace", "-s", "-o", out_path, in_path]

        # You can tweak thresholds with extra flags later if desired.

        try:
            proc = subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"potrace failed (exit {e.returncode}): {e.stderr.decode('utf-8', 'ignore')}"
            ) from e

        with open(out_path, "r", encoding="utf-8", errors="replace") as f:
            svg_text = f.read()
        return svg_text


def vectorize_image(
    input_bytes: bytes,
    max_colors: int = 8,
    smoothness: str = "medium",
    primitive_snap: bool = True,
) -> str:
    """
    High-level: convert uploaded bytes to BMP, run potrace, return SVG string.
    The extra params are placeholders for future improvements.
    """
    bmp_bytes = _png_bytes_to_bmp_bytes(input_bytes)
    svg_text = _run_potrace_on_bmp(bmp_bytes)
    return svg_text
