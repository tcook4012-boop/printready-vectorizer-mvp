# app/pipeline/logo_safe.py
import io
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import Optional, Tuple

from PIL import Image, ImageFilter

# =========================
# Small helpers
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


def _dehalo_to_white(im: Image.Image, bg=None, dist_thresh_sq: int = 11 * 11):
    """
    Replace pixels close to the background with pure white, then grow by ~2px.
    Stronger dist_thresh_sq eats more of the purple/grey fringe.
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

    # grow mask ~2px
    mask = mask.filter(ImageFilter.MaxFilter(size=5))
    # set to white where mask = 255
    white = Image.new("RGB", im.size, (255, 255, 255))
    im.paste(white, mask=mask)
    return im


def _upsample_2x(im: Image.Image) -> Image.Image:
    """
    3× upsample for smoother diagonals/curves.
    Name kept for backwards compatibility.
    """
    return im.resize((im.width * 3, im.height * 3), Image.Resampling.LANCZOS)


def _quantize_no_dither(im: Image.Image, k: int) -> Image.Image:
    """Median cut to k colors, no dithering."""
    q = im.quantize(colors=k, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    return q.convert("RGB")


def _gentle_regularize(im: Image.Image) -> Image.Image:
    """
    Mild clean-up:
    - MinFilter then MaxFilter to remove specks and close tiny gaps
    - Small Gaussian blur to smooth edges without overly rounding corners
    """
    im = im.filter(ImageFilter.MinFilter(3))
    im = im.filter(ImageFilter.MaxFilter(3))
    im = im.filter(ImageFilter.GaussianBlur(radius=0.7))
    return im


def _reindex_to_palette(im: Image.Image, k: int) -> Image.Image:
    """Snap smoothed image back to an exact K-color palette."""
    return _quantize_no_dither(im, k)


def _get_darkest_palette_color(pal_img: Image.Image) -> Tuple[int, int, int]:
    """
    Find the darkest color (by luma) among used palette entries.
    """
    if pal_img.mode != "P":
        tmp = pal_img.quantize(
            colors=min(16, (pal_img.getcolors() or [None] * 8).__len__()),
            method=Image.MEDIANCUT,
            dither=Image.Dither.NONE,
        )
        pal_img = tmp

    pal = pal_img.getpalette()
    used = set([idx for _, idx in (pal_img.getcolors(maxcolors=256) or [])])
    darkest, min_y = (0, 0, 0), 1e9
    for idx in used:
        r, g, b = pal[idx * 3 : idx * 3 + 3]
        y = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if y < min_y:
            min_y = y
            darkest = (r, g, b)
    return darkest


def _rgb_to_hex(c: Tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*c)


def _make_mask_for_color(im_rgb: Image.Image, target: Tuple[int, int, int]) -> Image.Image:
    """Binary mask where pixels equal the target color."""
    w, h = im_rgb.size
    mask = Image.new("1", (w, h), 0)
    mp = mask.load()
    px = im_rgb.load()
    for y in range(h):
        for x in range(w):
            if px[x, y] == target:
                mp[x, y] = 1
    return mask


def _write_temp_image(im: Image.Image, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    im.save(path)
    return path


def _run(cmd: list, input_bytes: Optional[bytes] = None):
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_bytes else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, err = proc.communicate(input=input_bytes)
    return proc.returncode, out, err


def _estimate_logo_palette_size(im: Image.Image, max_k: int = 8) -> int:
    """
    Estimate how many non-background colors there are and choose a
    palette size that preserves them while staying logo-friendly.
    """
    pal_img = im.convert("P", palette=Image.Palette.ADAPTIVE, colors=16)
    colors = pal_img.getcolors(maxcolors=256) or []
    if not colors:
        return 3

    pal = pal_img.getpalette()
    bg = _sample_bg_color(im)
    bg_thresh_sq = 20 * 20

    non_bg_count = 0
    for _, idx in colors:
        r, g, b = pal[idx * 3 : idx * 3 + 3]
        if _color_dist((r, g, b), bg) > bg_thresh_sq:
            non_bg_count += 1

    if non_bg_count <= 1:
        k = 3          # one logo color + background
    elif non_bg_count == 2:
        k = 5
    elif non_bg_count == 3:
        k = 6
    else:
        k = max_k      # richer logos → allow more clusters

    return max(3, min(k, max_k))


# =========================
# Main pipeline
# =========================


def vectorize_logo_safe_to_svg_bytes(image_bytes: bytes) -> bytes:
    """
    Logo-safe vectorization:
      - Palette-aware dehalo
      - Higher upsample for smooth curves
      - Fills via VTracer
      - Strokes on darkest color via Potrace
    """
    # 0) Load & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)
    im = _upsample_2x(im)

    # 1) Dehalo to kill background fringe (slightly stronger)
    im = _dehalo_to_white(im, bg=None, dist_thresh_sq=13 * 13)

    # 2) Palette estimation & quantization
    k = _estimate_logo_palette_size(im, max_k=8)
    im_q = _quantize_no_dither(im, k)

    # 3) Regularize & snap back to palette
    im_smooth = _gentle_regularize(im_q)
    im_final = _reindex_to_palette(im_smooth, k)

    # 4) Second dehalo pass (slightly tighter) to clean residual fringe
    im_final = _dehalo_to_white(im_final, bg=None, dist_thresh_sq=11 * 11)

    # 5A) Fills with VTracer
    png_path = _write_temp_image(im
