# backend/app/pipeline/logo_sign_mode.py

"""
Sign / text optimized vectorization pipeline.

Goals:
- Kill purple/gray AA halo around letters, numbers, borders, and stars.
- Keep flat fills for 1–4 color art (single-color logos, yard signs, etc.).
- Produce smoother curves and less jagged diagonals on text and flags.
"""

import io
import os
import subprocess
import tempfile
from typing import Tuple

from PIL import Image, ImageFilter


# ========= small helpers =========


def _to_srgb_rgba(im: Image.Image) -> Image.Image:
    """Normalize image to RGBA."""
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
    """Flatten alpha onto white background."""
    if im.mode != "RGBA":
        return im.convert("RGB")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    out = Image.alpha_composite(bg, im)
    return out.convert("RGB")


def _sample_bg_color(im: Image.Image) -> Tuple[int, int, int]:
    """
    Sample the 4 corners and take the median as 'background'.

    This works for:
    - white background with colored text
    - colored background with white text
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
    """Fast squared RGB distance."""
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _build_halo_mask(
    im: Image.Image,
    bg: Tuple[int, int, int],
    dist_thresh_sq: int = 35 * 35,
) -> Image.Image:
    """
    Build a mask for "halo" pixels close to the background color.

    dist_thresh_sq is intentionally large for sign art because shapes are
    big and we can afford aggressive halo removal without eating real strokes.
    """
    w, h = im.size
    mask = Image.new("L", (w, h), 0)
    mp = mask.load()
    px = im.load()

    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if _color_dist_sq((r, g, b), bg) <= dist_thresh_sq:
                mp[x, y] = 255

    # Grow mask ~1px so the entire AA fringe is covered
    mask = mask.filter(ImageFilter.MaxFilter(3))
    return mask


def _upsample_reasonable(im: Image.Image) -> Image.Image:
    """
    Upsample 2x for better curve fitting, unless already huge.

    This helps VTracer fit smoother spline curves on diagonal edges and circles.
    """
    w, h = im.size
    if max(w, h) >= 3000:
        return im
    return im.resize((w * 2, h * 2), Image.Resampling.LANCZOS)


def _estimate_unique_colors(im: Image.Image) -> int:
    """
    Rough estimate of how many 'meaningful' colors the artwork has.
    """
    thumb = im.copy()
    thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)
    pal = thumb.convert("P", palette=Image.Palette.ADAPTIVE, colors=16)
    colors = pal.getcolors(maxcolors=256) or []
    return len(colors)


def _quantize_no_dither(im: Image.Image, k: int) -> Image.Image:
    """
    Palette quantization with no dithering.

    We keep k small (2–6) for sign art so fills stay perfectly flat.
    """
    k = max(2, min(int(k), 6))
    q = im.quantize(colors=k, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    return q.convert("RGB")


def _regularize_sign_edges(im: Image.Image) -> Image.Image:
    """
    Stronger regularization for sign/text art.

    - MinFilter/MaxFilter smooth tiny bites and gaps in strokes.
    - A small Gaussian blur softens stair-steps on diagonals/curves.
    """
    # NOTE: Pillow requires an odd filter size (3, 5, ...).
    im = im.filter(ImageFilter.MinFilter(3))
    im = im.filter(ImageFilter.MaxFilter(3))
    im = im.filter(ImageFilter.GaussianBlur(radius=0.4))
    return im


def _write_temp_image(im: Image.Image) -> Tuple[str, tempfile.TemporaryDirectory]:
    """
    Save image in a TemporaryDirectory and return (png_path, tmpdir).
    """
    tmpdir = tempfile.TemporaryDirectory()
    png_path = os.path.join(tmpdir.name, "sign_input.png")
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
    Sign / text pipeline.

    Typical inputs:
    - Single-color signs (any color) with text and shapes.
    - Political yard signs like MURILLO.
    - Phone-number yard signs like PECANS.
    - Logos with a lot of text but low overall color count.

    Steps:
    1) Load and flatten onto solid background.
    2) Build and apply a strong halo mask near the background color.
    3) Upsample 2x (if not enormous).
    4) Quantize to a small palette (2–6 colors), no dithering.
    5) Regularize edges for cleaner vectors.
    6) Run VTracer (spline, color).
    """
    # 0) Load & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im_rgb = _composite_over_white(im)

    # 1) Strong halo cleanup toward background color
    bg = _sample_bg_color(im_rgb)
    halo_mask = _build_halo_mask(im_rgb, bg, dist_thresh_sq=35 * 35)

    bg_img = Image.new("RGB", im_rgb.size, bg)
    im_rgb.paste(bg_img, mask=halo_mask)

    # 2) Upsample for smoother curve fitting
    im_rgb = _upsample_reasonable(im_rgb)

    # 3) Estimate palette size and quantize
    approx_unique = _estimate_unique_colors(im_rgb)

    if approx_unique <= 2:
        k = 2
    elif approx_unique == 3:
        k = 3
    elif approx_unique == 4:
        k = 4
    else:
        k = min(6, approx_unique)

    im_q = _quantize_no_dither(im_rgb, k)

    # 4) Edge regularization to reduce jaggedness
    im_reg = _regularize_sign_edges(im_q)

    # 5) Vectorize with VTracer
    png_path, tmpdir = _write_temp_image(im_reg)
    try:
        svg_path = os.path.join(tmpdir.name, "sign_output.svg")

        cmd = [
            "vtracer",
            "--input", png_path,
            "--output", svg_path,
            "--mode", "spline",
            "--colormode", "color",
            "--filter_speckle", "3",
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
