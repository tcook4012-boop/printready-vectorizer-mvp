# backend/app/pipeline/logo_sign_mode.py

import io
import os
import subprocess
import tempfile
from typing import Tuple

from PIL import Image, ImageFilter


# ========= helpers =========


def _to_srgb_rgba(im: Image.Image) -> Image.Image:
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
    if im.mode != "RGBA":
        return im.convert("RGB")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    out = Image.alpha_composite(bg, im)
    return out.convert("RGB")


def _sample_bg_color(im: Image.Image) -> Tuple[int, int, int]:
    """
    Guess the background from the 4 near-corners
    (robust against 1px borders).
    """
    w, h = im.size
    pts = [
        im.getpixel((1, 1)),
        im.getpixel((w - 2, 1)),
        im.getpixel((1, h - 2)),
        im.getpixel((w - 2, h - 2)),
    ]
    rs = sorted(p[0] for p in pts)
    gs = sorted(p[1] for p in pts)
    bs = sorted(p[2] for p in pts)
    return (rs[1], gs[1], bs[1])


def _color_dist_sq(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _brightness(c: Tuple[int, int, int]) -> int:
    # standard luma approximation
    return (c[0] * 299 + c[1] * 587 + c[2] * 114) // 1000


def _dehalo_sign(im: Image.Image, bg: Tuple[int, int, int]) -> Image.Image:
    """
    Aggressive dehalo tuned for flat signs.

    Anything very close to background, or "almost white/black" when the
    background is white/black, is snapped to exact bg.
    """
    im = im.copy()
    px = im.load()
    w, h = im.size

    bg_br = _brightness(bg)
    bg_is_light = bg_br > 200
    bg_is_dark = bg_br < 55

    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            d2 = _color_dist_sq((r, g, b), bg)

            # very close to background color: send to bg
            if d2 <= 10 * 10:
                px[x, y] = bg
                continue

            br = _brightness((r, g, b))

            # if background is white-ish, kill almost-white fringe
            if bg_is_light and br > 245:
                px[x, y] = bg
            # if background is dark-ish, kill almost-black fringe
            elif bg_is_dark and br < 10:
                px[x, y] = bg

    return im


def _upsample_2x(im: Image.Image) -> Image.Image:
    w, h = im.size
    if max(w, h) >= 3000:
        # avoid blowing memory on huge billboards
        return im
    return im.resize((w * 2, h * 2), Image.Resampling.LANCZOS)


def _quantize_sign(im: Image.Image, k: int) -> Image.Image:
    """
    Palette quantizer for signs. We keep k small so halos cannot
    become their own color cluster.
    """
    k = max(2, min(k, 6))
    q = im.convert(
        "P",
        palette=Image.Palette.ADAPTIVE,
        colors=k,
        dither=Image.Dither.NONE,
    )
    return q.convert("RGB")


def _post_snap_whites_blacks(im: Image.Image) -> Image.Image:
    """
    After smoothing/quantization, force "almost white" and "almost black"
    to exact 255/0. This removes inner haze in stars & letters.
    """
    im = im.copy()
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            br = _brightness((r, g, b))

            if br > 250:
                px[x, y] = (255, 255, 255)
            elif br < 5:
                px[x, y] = (0, 0, 0)

    return im


def _regularize_sign_shapes(im: Image.Image) -> Image.Image:
    """
    Slight morphological closing + light blur:
      - closes small gaps in letters/stars
      - rounds jaggy diagonals
    """
    im = im.filter(ImageFilter.MinFilter(3))
    im = im.filter(ImageFilter.MaxFilter(3))
    im = im.filter(ImageFilter.GaussianBlur(radius=0.6))
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


# ========= main sign pipeline =========


def vectorize_logo_sign_mode_to_svg_bytes(image_bytes: bytes) -> bytes:
    """
    High-clarity sign/text pipeline.

    Targets:
      - Kill purple/gray halos around letters & stars.
      - Clean, blocky edges on letters.
      - Smoother curves on stripes / arrows.
    """
    # 0) load & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)
    im = _upsample_2x(im)

    # 1) aggressive dehalo in background space
    bg = _sample_bg_color(im)
    im = im.convert("RGB")
    im = _dehalo_sign(im, bg)

    # 2) estimate palette size and clamp to 2–4
    thumb = im.copy()
    thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)
    pal = thumb.convert("P", palette=Image.Palette.ADAPTIVE, colors=8)
    colors = pal.getcolors(maxcolors=256) or []
    approx_unique = len(colors)

    if approx_unique <= 2:
        k = 2
    elif approx_unique <= 3:
        k = 3
    else:
        k = 4  # most signs are 2–3 colors; 4 is a safe ceiling

    # 3) quantize → regularize → re-quantize for crisp flats
    im = _quantize_sign(im, k)
    im = _regularize_sign_shapes(im)
    im = _quantize_sign(im, k)
    im = _post_snap_whites_blacks(im)

    # 4) Vectorize with VTracer (polygon mode for straighter edges)
    png_path, tmpdir = _write_temp_image(im)
    try:
        svg_path = os.path.join(tmpdir.name, "out.svg")

        cmd = [
            "vtracer",
            "--input", png_path,
            "--output", svg_path,
            "--mode", "polygon",
            "--colormode", "color",
            "--filter_speckle", "4",
        ]

        code, out, err = _run(cmd)
        if code != 0 or not os.path.exists(svg_path):
            msg = (
                err.decode("utf-8", "ignore")
                if isinstance(err, (bytes, bytearray))
                else str(err)
            )
            raise RuntimeError(f"vtracer failed (sign mode): {msg}")

        with open(svg_path, "rb") as f:
            svg_bytes = f.read()
    finally:
        tmpdir.cleanup()

    return svg_bytes
