# app/vectorizer/pipeline.py
import io
import os
import subprocess
import tempfile
from typing import Optional

from PIL import Image


def _otsu_threshold(gray: Image.Image) -> int:
    """
    Compute an Otsu threshold for a grayscale PIL image (mode 'L').
    Returns an integer in [0, 255].
    """
    hist = gray.histogram()  # 256 bins
    total = sum(hist)
    sum_total = 0
    for i, h in enumerate(hist):
        sum_total += i * h

    sum_b = 0
    w_b = 0
    max_between = -1.0
    threshold = 127

    for i in range(256):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break

        sum_b += i * hist[i]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2  # between-class variance

        if between > max_between:
            max_between = between
            threshold = i

    return threshold


def _bytes_to_pbm(image_bytes: bytes, max_colors: int = 8) -> bytes:
    """
    Convert arbitrary raster bytes (jpg/png/etc.) to a monochrome PBM
    bytes buffer suitable for potrace input.
    """
    # Load & normalize
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Optional palette reduction before thresholding (can improve edge finding)
    if max_colors and max_colors > 0:
        # quantize to a small palette to reduce noise
        img = img.quantize(colors=max_colors, method=Image.MEDIANCUT).convert("RGB")

    # Grayscale -> auto threshold -> bilevel
    gray = img.convert("L")
    th = _otsu_threshold(gray)
    # Threshold to bilevel (0 or 255) then force mode '1'
    bw = gray.point(lambda p: 255 if p >= th else 0).convert("1")

    # Save to PBM (Portable BitMap). PIL chooses PBM from extension.
    with io.BytesIO() as pbm_buf:
        # Using extension-driven format
        with tempfile.NamedTemporaryFile(suffix=".pbm", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            bw.save(tmp_path)  # writes PBM because of .pbm extension
            with open(tmp_path, "rb") as f:
                pbm_bytes = f.read()
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return pbm_bytes


def _run_potrace_on_pbm(pbm_bytes: bytes) -> str:
    """
    Run potrace on PBM bytes and return SVG string.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        pbm_path = os.path.join(tmpdir, "in.pbm")
        svg_path = os.path.join(tmpdir, "out.svg")

        with open(pbm_path, "wb") as f:
            f.write(pbm_bytes)

        # Build potrace command. "-s" outputs SVG.
        cmd = ["potrace", "-s", "-o", svg_path, pbm_path]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"potrace failed (exit {e.returncode}): {e.stderr.decode('utf-8', errors='ignore')}"
            )

        # Read back the SVG
        with open(svg_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


def vectorize_image(
    image_bytes: bytes,
    max_colors: int = 8,
    smoothness: Optional[str] = "medium",
    primitive_snap: Optional[bool] = False,
) -> str:
    """
    Public API: convert a raster image (bytes) into SVG using potrace.

    Args:
        image_bytes: Raw bytes of the uploaded image (jpg/png/etc).
        max_colors: Palette reduction before thresholding (helps denoise).
        smoothness: Placeholder knob (kept for compatibility/UI).
        primitive_snap: Placeholder knob (kept for compatibility/UI).

    Returns:
        SVG string.
    """
    pbm_bytes = _bytes_to_pbm(image_bytes, max_colors=max_colors)
    svg_text = _run_potrace_on_pbm(pbm_bytes)
    return svg_text
