# backend/app/pipeline/logo_sign_mode.py

"""
Sign / flat-text optimized vectorization pipeline.

Goals for PECANS / Murillo / political signs / flat logos:
- No purple/gray halo around letters, shapes, or stars.
- No interior haze inside white shapes (e.g., stars).
- Very crisp straight edges and smooth curves.
- Flat fills only (no strokes in the final SVG).

This pipeline is intentionally MORE aggressive than the mascot pipeline:
we can blur and regularize more because signs are simple, flat-color art.
"""

import io
import os
import subprocess
import tempfile
from typing import Tuple, Optional

from PIL import Image, ImageFilter


# ========= small helpers =========

def _to_srgb_rgba(im: Image.Image) -> Image.Image:
    """Normalize to RGBA in a predictable way."""
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
    """
    Flatten any transparency over pure white.

    This removes semi-transparent edges which would otherwise turn into
    purple/gray fringes when quantized.
    """
    if im.mode != "RGBA":
        return im.convert("RGB")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    out = Image.alpha_composite(bg, im)
    return out.convert("RGB")


def _sample_bg_color(im: Image.Image) -> Tuple[int, int, int]:
    """
    Guess the background color by looking at the 4 corners and taking
    the median in each channel.
    """
    w, h = im.size
    pts = [
        im.getpixel((0, 0)),
        im.getpixel((w - 1, 0)),
        im.getpixel((0, h - 1)),
        im.getpixel((w - 1, h - 1)),
    ]
    rs = sorted(p[0] for p in pts)
    gs = sorted(p[1] for p in pts)
    bs = sorted(p[2] for p in pts)
    return (rs[1], gs[1], bs[1])


def _color_dist_sq(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _hard_dehalo_to_bg(
    im: Image.Image,
    bg: Optional[Tuple[int, int, int]] = None,
    thresh_sq: int = 16 * 16,
) -> Image.Image:
    """
    Strong dehalo for flat signs.

    Any pixel sufficiently close to background is turned into *exact*
    background color, and then we dilate that region ~2px to eat away
    all anti-aliased fringe.

    This is intentionally more aggressive than the mascot pipeline.
    """
    im = im.copy()
    if bg is None:
        bg = _sample_bg_color(im)

    w, h = im.size
    pix = im.load()

    # Build a mask of "background-like" pixels
    mask = Image.new("L", im.size, 0)
    mp = mask.load()

    for y in range(h):
        for x in range(w):
            r, g, b = pix[x, y]
            if _color_dist_sq((r, g, b), bg) <= thresh_sq:
                mp[x, y] = 255

    # Grow that mask a bit (2–3 pixels) to remove fringe
    # Pillow filters require an ODD size.
    mask = mask.filter(ImageFilter.MaxFilter(5))

    # Paste exact background color wherever the mask is white
    bg_img = Image.new("RGB", im.size, bg)
    im.paste(bg_img, mask=mask)

    return im


def _upsample_for_signs(im: Image.Image) -> Image.Image:
    """
    Upsample 2x to give VTracer more pixels to work with,
    but avoid blowing up *huge* inputs.
    """
    w, h = im.size
    max_dim = max(w, h)
    if max_dim >= 3000:
        # already huge, don't upsample more
        return im
    return im.resize((w * 2, h * 2), Image.Resampling.LANCZOS)


def _estimate_unique_colors(im: Image.Image) -> int:
    """
    Rough estimate of color count on a small thumbnail.
    """
    thumb = im.copy()
    thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)
    pal = thumb.convert("P", palette=Image.Palette.ADAPTIVE, colors=8)
    colors = pal.getcolors(maxcolors=256) or []
    return len(colors)


def _quantize_flat_palette(im: Image.Image, k: int) -> Image.Image:
    """
    Quantize to k colors with NO dithering.

    This is what enforces true flat fills (no gradients).
    """
    k = max(2, min(int(k), 8))
    q = im.convert(
        "P",
        palette=Image.Palette.ADAPTIVE,
        colors=k,
        dither=Image.Dither.NONE,
    )
    return q.convert("RGB")


def _regularize_sign_shapes(im: Image.Image, k: int) -> Image.Image:
    """
    Two-stage regularization:
      1) Blur slightly to smooth stair-steps and curves.
      2) Quantize BACK to the same palette to snap to flat fills.

    This removes interior haze (like in white stars) and cleans edges.
    """
    # Slight blur (stronger than mascot mode, but fine for signs)
    im = im.filter(ImageFilter.GaussianBlur(radius=1.3))
    # Snap back to a flat palette
    im = _quantize_flat_palette(im, k=k)
    return im


def _write_temp_image(im: Image.Image) -> Tuple[str, tempfile.TemporaryDirectory]:
    tmpdir = tempfile.TemporaryDirectory()
    png_path = os.path.join(tmpdir.name, "in.png")
    im.save(png_path, "PNG")
    return png_path, tmpdir


def _run(cmd):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


# ========= main pipeline =========

def vectorize_logo_sign_mode_to_svg_bytes(image_bytes: bytes) -> bytes:
    """
    Sign / flat-text pipeline.

    Steps:
      - Composite over white (remove alpha).
      - Hard dehalo versus background (kills halo fully).
      - Upsample 2x.
      - Quantize to 2–4 flat colors (depending on input).
      - Smooth + re-quantize to flatten interior haze.
      - Vectorize with VTracer (fills only).
    """
    # 0) Load & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)

    # 1) Strong dehalo against inferred background
    bg = _sample_bg_color(im)
    im = _hard_dehalo_to_bg(im, bg=bg, thresh_sq=16 * 16)

    # 2) Upsample for smoother curves
    im = _upsample_for_signs(im)

    # 3) Estimate color count, then clamp between 2 and 4
    approx_unique = _estimate_unique_colors(im)
    if approx_unique <= 2:
        k = 2
    elif approx_unique == 3:
        k = 3
    else:
        k = 4

    # 4) Quantize to flat palette
    im = _quantize_flat_palette(im, k=k)

    # 5) Smooth shapes and snap back to palette
    im = _regularize_sign_shapes(im, k=k)

    # 6) Run VTracer once (fills only, no stroke overlay)
    png_path, tmpdir = _write_temp_image(im)
    try:
        svg_path = os.path.join(tmpdir.name, "out.svg")

        cmd = [
            "vtracer",
            "--input", png_path,
            "--output", svg_path,
            "--mode", "spline",
            "--colormode", "color",
            "--filter_speckle", "8",
        ]

        code, out, err = _run(cmd)
        if code != 0 or not os.path.exists(svg_path):
            msg = err.decode("utf-8", "ignore") if isinstance(err, (bytes, bytearray)) else str(err)
            raise RuntimeError(f"vtracer failed (sign mode): {msg}")

        with open(svg_path, "rb") as f:
            svg_bytes = f.read()
    finally:
        tmpdir.cleanup()

    return svg_bytes
