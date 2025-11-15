import io
import os
import subprocess
import tempfile
from typing import Tuple

from PIL import Image, ImageFilter


# ========= small helpers (light copy of logo_safe) =========

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
    """Sample the 4 corners and take the median as 'background'."""
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


def _dehalo_to_white(im: Image.Image, bg: Tuple[int, int, int]) -> Image.Image:
    """
    Very light dehalo: anything extremely close to background becomes pure white.

    For mascot logos we *do not* want heavy shrinking of shapes, just removal
    of the faint anti-alias blend around edges.
    """
    pix = im.load()
    w, h = im.size
    # threshold ~ 8 in RGB distance
    thresh_sq = 8 * 8
    for y in range(h):
        for x in range(w):
            r, g, b = pix[x, y]
            if _color_dist_sq((r, g, b), bg) <= thresh_sq:
                pix[x, y] = (255, 255, 255)
    return im


def _upsample_2x(im: Image.Image) -> Image.Image:
    w, h = im.size
    if max(w, h) >= 3000:
        # avoid blowing up memory on huge inputs
        return im
    return im.resize((w * 2, h * 2), Image.Resampling.LANCZOS)


def _quantize_palette(im: Image.Image, k: int) -> Image.Image:
    """
    Palette quantization with *no* dithering.

    We keep k relatively high (5–8) to preserve distinct uniform fills like
    coat vs beard vs outline.
    """
    k = max(2, min(int(k), 16))
    return (
        im.convert("P", palette=Image.Palette.ADAPTIVE, colors=k,
                  dither=Image.Dither.NONE)
          .convert("RGB")
    )


def _gentle_regularize_logo(im: Image.Image) -> Image.Image:
    """
    Gentle shape regularization for mascot logos.

    We apply a very small blur only, no min/max morphological operations.
    This avoids 'shrinking' details or creating dark outlines.
    """
    # radius 0.6–0.8 is enough to smooth stair-steps without eating corners
    im = im.filter(ImageFilter.GaussianBlur(radius=0.7))
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


def vectorize_logo_logo_mode_to_svg_bytes(image_bytes: bytes) -> bytes:
    """
    Mascot / complex logo pipeline.

    Goals:
    - Preserve distinct fills (coat vs beard vs outline).
    - Avoid red/brown outlines around shapes.
    - Keep medium-smooth curves without erasing detail.
    """
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)

    # 1) very light dehalo to clean background fringe
    bg = _sample_bg_color(im)
    im = im.convert("RGB")
    im = _dehalo_to_white(im, bg)

    # 2) modest 2x upsample (if not already huge)
    im = _upsample_2x(im)

    # 3) estimate how many colors we actually need, cap 8, min 5
    thumb = im.copy()
    thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)
    pal = thumb.convert("P", palette=Image.Palette.ADAPTIVE, colors=16)
    colors = pal.getcolors(maxcolors=256) or []
    approx_unique = len(colors)
    k = max(5, min(8, approx_unique))

    # 4) quantize to stable palette without dithering
    im = _quantize_palette(im, k=k)

    # 5) gentle smoothing to remove stair-steps, *after* palette locking
    im = _gentle_regularize_logo(im)

    # 6) Run vtracer directly (no extra Potrace overlay here).
    png_path, tmpdir = _write_temp_image(im)
    try:
        svg_path = os.path.join(tmpdir.name, "out.svg")

        # Slight bias toward smoothness but still preserving details.
        cmd = [
            "vtracer",
            "--input", png_path,
            "--output", svg_path,
            "--mode", "spline",
            "--colormode", "color",
            "--filter_speckle", "4",
        ]

        code, out, err = _run(cmd)
        if code != 0 or not os.path.exists(svg_path):
            msg = err.decode("utf-8", "ignore") if isinstance(err, (bytes, bytearray)) else str(err)
            raise RuntimeError(f"vtracer failed (logo mode): {msg}")

        with open(svg_path, "rb") as f:
            svg_bytes = f.read()
    finally:
        tmpdir.cleanup()

    return svg_bytes
