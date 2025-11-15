# backend/app/pipeline/logo_logo_mode.py

"""
Logo-focused variant of the logo_safe pipeline.

This is intended for mascot / logo art like ELON where we want:
  - Multiple flat colors preserved (coat, beard, hat, letters, background)
  - No extra outline strokes
  - Less aggressive smoothing than the sign pipeline (keep facial detail)

Signs (PECANS, Murillo) should continue to use the main logo_safe pipeline.
"""

import io
import os
import subprocess
import tempfile
from typing import Optional, Tuple

from PIL import Image, ImageFilter


# =========================
# Small helpers (similar to logo_safe, tuned for logos)
# =========================

def _to_srgb_rgba(im: Image.Image) -> Image.Image:
    """Normalize to RGBA, sRGB-ish."""
    if im.mode in ("P", "L"):
        im = im.convert("RGBA")
    elif im.mode == "RGB":
        im = im.convert("RGBA")
    elif im.mode == "LA":
        im = im.convert("RGBA")
    elif im.mode == "RGBA":
        pass
    else:
        im = im.convert("RGBA")
    return im


def _composite_over_white(im: Image.Image) -> Image.Image:
    """Flatten alpha over white to kill semi-transparent halos."""
    if im.mode != "RGBA":
        return im.convert("RGB")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    out = Image.alpha_composite(bg, im)
    return out.convert("RGB")


def _sample_bg_color(im: Image.Image) -> Tuple[int, int, int]:
    """Very quick modal of 4 corners to guess background color."""
    w, h = im.size
    pts = [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]
    samples = [im.getpixel(p) for p in pts]
    counts = {}
    for c in samples:
        counts[c] = counts.get(c, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _color_dist(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    """Fast RGB squared distance."""
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _dehalo_to_white(
    im: Image.Image,
    bg: Optional[Tuple[int, int, int]] = None,
    dist_thresh_sq: int = 9 * 9,
) -> Image.Image:
    """
    Replace pixels close to the background with pure white, then grow by ~1px.

    Slightly gentler than the sign pipeline: we still remove fringe but avoid
    eating into fine features (eyes, facial lines).
    """
    im = im.copy()
    w, h = im.size
    if bg is None:
        bg = _sample_bg_color(im)

    px = im.load()
    mask = Image.new("L", im.size, 0)
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if _color_dist(p, bg) <= dist_thresh_sq:
                mp[x, y] = 255

    # grow mask ~1px instead of 2–3px
    mask = mask.filter(ImageFilter.MaxFilter(size=3))
    white = Image.new("RGB", im.size, (255, 255, 255))
    im.paste(white, mask=mask)
    return im


def _upsample_2x(im: Image.Image) -> Image.Image:
    return im.resize((im.width * 2, im.height * 2), Image.Resampling.LANCZOS)


def _quantize_no_dither(im: Image.Image, k: int) -> Image.Image:
    """Median cut to k colors, no dithering."""
    q = im.quantize(colors=k, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    return q.convert("RGB")


def _gentle_regularize_logo(im: Image.Image) -> Image.Image:
    """
    Slightly gentler regularization for logos:

    - small Min/Max filters to close tiny gaps without shrinking shapes
    - lighter blur to keep edges smoother but not melted

    NOTE: Pillow requires an ODD filter size (3, 5, ...) for MinFilter/MaxFilter.
    """
    im = im.filter(ImageFilter.MinFilter(3))
    im = im.filter(ImageFilter.MaxFilter(3))
    im = im.filter(ImageFilter.GaussianBlur(radius=0.7))
    return im


def _reindex_to_palette(im: Image.Image, k: int) -> Image.Image:
    """Snap smoothed image back to an exact K-color palette."""
    return _quantize_no_dither(im, k)


def _write_temp_image(im: Image.Image, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    im.save(path)
    return path


def _run(cmd: list, input_bytes: Optional[bytes] = None) -> Tuple[int, bytes, bytes]:
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_bytes else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, err = proc.communicate(input=input_bytes)
    return proc.returncode, out, err


# =========================
# Main logo pipeline
# =========================

def vectorize_logo_logo_mode_to_svg_bytes(image_bytes: bytes) -> bytes:
    """
    Logo-focused vectorization:

      - Upsample 2x
      - Gentle dehalo over white
      - Palette clamp with slightly higher cap (up to 6 colors)
      - Regularize edges (lighter than sign pipeline)
      - VTracer fills ONLY (no Potrace stroke overlay)

    This should help ELON keep:
      - separate coat / beard / hat / letter colors
      - inner details (eye, buttons)
      - smooth curves without the extra red outline.
    """
    # 0) Load & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)
    im = _upsample_2x(im)

    # 1) Dehalo against white-ish background
    im = _dehalo_to_white(im, bg=None, dist_thresh_sq=9 * 9)

    # 2) Estimate unique-ish colors and choose palette size.
    pal_img = im.convert("P", palette=Image.Palette.ADAPTIVE, colors=8)
    approx_unique = len(pal_img.getcolors() or [])

    # Bound between 3 and 6 colors; try to keep enough breathing room.
    if approx_unique <= 3:
        k = 3
    elif approx_unique == 4:
        k = 4
    else:
        k = min(6, approx_unique)

    # 3) Quantize (no dithering)
    im_q = _quantize_no_dither(im, k)

    # 4) Gentler regularization and snap-to-palette
    im_smooth = _gentle_regularize_logo(im_q)
    im_final = _reindex_to_palette(im_smooth, k)

    # 5) Single-pass vectorization with VTracer (fills only)
    png_path = _write_temp_image(im_final, ".png")
    svg_fd, svg_path = tempfile.mkstemp(suffix=".svg")
    os.close(svg_fd)

    rc, _, err = _run(["vtracer", "-i", png_path, "-o", svg_path])
    if rc != 0:
        raise RuntimeError(
            f"vtracer failed (logo mode): {err.decode('utf-8', 'ignore')}"
        )

    with open(svg_path, "rb") as f:
        svg_bytes = f.read()

    # Cleanup
    for p in (png_path, svg_path):
        try:
            os.remove(p)
        except OSError:
            pass

    return svg_bytes
