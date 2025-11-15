# backend/app/pipeline/logo_sign_mode.py

"""
High-clarity sign / text pipeline (Option A).

This is for:
  - Yard signs
  - Political signs
  - Simple flat logos with 1–3 solid colors
  - Phone numbers, arrows, big block text, etc.

Goals:
  - ZERO purple/gray haze around letters, stars, or shapes
  - Very sharp, geometric edges
  - Solid fills (no speckle, no “dirty” pixels)
  - Keep the INTENT of the design, not the raster artifacts
"""

import io
import os
import subprocess
import tempfile
from typing import Tuple

from PIL import Image, ImageFilter


# ========= small helpers =========


def _to_srgb_rgba(im: Image.Image) -> Image.Image:
    """Normalize to RGBA."""
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
    """Flatten any transparency over white."""
    if im.mode != "RGBA":
        return im.convert("RGB")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    out = Image.alpha_composite(bg, im)
    return out.convert("RGB")


def _upsample_2x_if_reasonable(im: Image.Image) -> Image.Image:
    """
    Upscale 2x for smoother geometry, but avoid explosions
    on already-huge input art.
    """
    w, h = im.size
    if max(w, h) >= 3000:
        return im
    return im.resize((w * 2, h * 2), Image.Resampling.LANCZOS)


def _quantize_flat_sign_palette(im: Image.Image, max_colors: int = 3) -> Image.Image:
    """
    Aggressive palette clamp for signs.

    We intentionally collapse fringe colors (purple/gray haze) into the
    nearest of a very small set of solid colors (1–3).
    NO dithering, to keep hard, flat fills.
    """
    max_colors = max(2, min(int(max_colors), 6))
    pal = im.convert(
        "P",
        palette=Image.Palette.ADAPTIVE,
        colors=max_colors,
        dither=Image.Dither.NONE,
    )
    return pal.convert("RGB")


def _binary_cleanup(im: Image.Image) -> Image.Image:
    """
    Clean residual stair-steps and tiny speckles.

    We use a small MinFilter/MaxFilter pair (odd size = 3) to:
      - close hairline gaps
      - knock out single-pixel noise
    followed by a *very* light blur to smooth diagonals.
    """
    # Morphological closing-ish behavior
    im = im.filter(ImageFilter.MinFilter(3))
    im = im.filter(ImageFilter.MaxFilter(3))

    # Ultra-light blur: just enough to smooth jaggies
    im = im.filter(ImageFilter.GaussianBlur(radius=0.4))
    return im


def _write_temp_png(im: Image.Image) -> Tuple[str, tempfile.TemporaryDirectory]:
    """
    Save image into a TemporaryDirectory and return (path, tmpdir).
    Caller must keep tmpdir alive until done.
    """
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


# ========= main sign pipeline =========


def vectorize_logo_sign_mode_to_svg_bytes(image_bytes: bytes) -> bytes:
    """
    Sign / text vectorization (Option A).

    Processing steps:
      1) Normalize to sRGB & flatten over white.
      2) Modest 2x upsample for clean geometry (if not huge).
      3) Palette clamp to 2–3 colors, NO dithering.
      4) Morphological cleanup + tiny blur.
      5) Run vtracer in color mode with default spline settings.
    """
    # 1) Decode & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)

    # 2) Upsample for smoother curves (within memory limits)
    im = _upsample_2x_if_reasonable(im)

    # 3) Aggressive palette clamp: crush haze into solid fills
    #    For most signs, 2 or 3 colors is ideal.
    im = _quantize_flat_sign_palette(im, max_colors=3)

    # 4) Geometric cleanup
    im = _binary_cleanup(im)

    # 5) Save to temp PNG & run vtracer
    png_path, tmpdir = _write_temp_png(im)
    try:
        svg_path = os.path.join(tmpdir.name, "out.svg")

        cmd = [
            "vtracer",
            "-i",
            png_path,
            "-o",
            svg_path,
            # Defaults already give spline/color;
            # we avoid exotic flags to keep it robust.
        ]

        code, out, err = _run(cmd)
        if code != 0 or not os.path.exists(svg_path):
            msg = err.decode("utf-8", "ignore") if isinstance(
                err, (bytes, bytearray)
            ) else str(err)
            raise RuntimeError(f"vtracer failed (sign mode): {msg}")

        with open(svg_path, "rb") as f:
            svg_bytes = f.read()
    finally:
        tmpdir.cleanup()

    return svg_bytes
