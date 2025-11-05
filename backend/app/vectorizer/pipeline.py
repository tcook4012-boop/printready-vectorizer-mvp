import io
import os
import subprocess
import tempfile
from typing import Tuple

from PIL import Image, ImageOps


def _otsu_threshold(im_gray: Image.Image) -> int:
    """Compute Otsu threshold from a grayscale Pillow image (mode 'L')."""
    hist = im_gray.histogram()  # length 256
    total = sum(hist)
    sum_total = sum(i * hist[i] for i in range(256))

    sumB = 0.0
    wB = 0.0
    var_max = 0.0
    threshold = 127

    for t in range(256):
        wB += hist[t]
        if wB == 0:
            continue
        wF = total - wB
        if wF == 0:
            break
        sumB += t * hist[t]
        mB = sumB / wB
        mF = (sum_total - sumB) / wF
        between = wB * wF * (mB - mF) * (mB - mF)
        if between > var_max:
            var_max = between
            threshold = t

    return threshold


def _to_bilevel_pbm(image_bytes: bytes) -> Image.Image:
    """Convert input bytes to a bilevel (mode '1') image suitable for potrace."""
    with Image.open(io.BytesIO(image_bytes)) as im:
        # Convert to grayscale first
        im = im.convert("L")

        # Otsu threshold -> binary
        thr = _otsu_threshold(im)
        bw = im.point(lambda p: 255 if p > thr else 0, mode="1")  # white bg, black fg ideally

        # Potrace traces BLACK pixels as shapes. Ensure we truly have black shapes.
        # If all-white, invert. If almost-all black, invert too.
        # For mode '1', getcolors() returns [(count, 0 or 255), ...]
        colors = dict((v, c) for c, v in (bw.getcolors() or []))  # {0: black_count, 255: white_count}
        black_count = colors.get(0, 0)
        white_count = colors.get(255, 0)
        total = black_count + white_count

        if total == 0:
            # fallback: force a thresholded image again
            bw = im.point(lambda p: 0 if p < 128 else 255, mode="1")
            colors = dict((v, c) for c, v in (bw.getcolors() or []))
            black_count = colors.get(0, 0)
            white_count = colors.get(255, 0)
            total = black_count + white_count

        # Heuristics to guarantee black shapes on white background
        if black_count == 0:
            # No shapes at all -> invert
            bw = ImageOps.invert(bw.convert("L")).point(lambda p: 0 if p < 128 else 255, mode="1")
        else:
            # If >95% pixels are black, likely inverted background; invert it
            if total > 0 and black_count / total > 0.95:
                bw = ImageOps.invert(bw.convert("L")).point(lambda p: 0 if p < 128 else 255, mode="1")

        return bw


def _run_potrace(pbm_img: Image.Image) -> str:
    """Run potrace on a bilevel image object and return the SVG text."""
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "in.pbm")
        out_path = os.path.join(tmpdir, "out.svg")

        # IMPORTANT: saving a mode '1' image with format='PPM' yields PBM
        pbm_img.save(in_path, format="PPM")  # PBM/PGM/PPM family; mode '1' -> PBM

        # You can tune parameters here: -t (turnpolicy), -a (alphamax), -u (unit), etc.
        cmd = ["potrace", "-s", "-o", out_path, in_path]

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"potrace failed (exit {e.returncode}): {e.stderr.decode(errors='ignore')}"
            ) from e

        with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
            svg_text = f.read()

        return svg_text


def vectorize_image(
    image_bytes: bytes,
    max_colors: int = 8,
    smoothness: str = "medium",
    primitive_snap: bool = True,
) -> str:
    """
    Convert an uploaded raster image to SVG by thresholding to PBM and tracing with potrace.
    Note: max_colors, smoothness, primitive_snap are accepted for API compatibility but
    are not used by potrace (single-color trace).
    """
    pbm = _to_bilevel_pbm(image_bytes)
    svg_text = _run_potrace(pbm)

    # Safety: if SVG is suspiciously tiny, hint that thresholding may have failed
    if len(svg_text.strip()) < 50:
        # Try a reversed threshold once as a fallback
        pbm_inv = ImageOps.invert(pbm.convert("L")).point(lambda p: 0 if p < 128 else 255, mode="1")
        try:
            svg_text = _run_potrace(pbm_inv)
        except Exception:
            pass

    return svg_text
