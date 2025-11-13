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
    return im.resize((im.width * 2, im.height * 2), Image.Resampling.LANCZOS)


def _quantize_no_dither(im: Image.Image, k: int) -> Image.Image:
    """Median cut to k colors, no dithering."""
    q = im.quantize(colors=k, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    return q.convert("RGB")


def _gentle_regularize(im: Image.Image) -> Image.Image:
    """
    Light morphological clean-up:
    Min -> Max (size=3) to close tiny gaps, then small blur to smooth edges.
    Slightly stronger blur to smooth curves/stars more.
    """
    im = im.filter(ImageFilter.MinFilter(3))
    im = im.filter(ImageFilter.MaxFilter(3))
    im = im.filter(ImageFilter.GaussianBlur(radius=1.1))  # was 0.8
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


def _run(cmd: list, input_bytes: Optional[bytes] = None) -> Tuple[int, bytes, bytes]:
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_bytes else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, err = proc.communicate(input=input_bytes)
    return proc.returncode, out, err


def _estimate_logo_palette_size(im: Image.Image, max_k: int = 6) -> int:
    """
    Estimate how many *non-background* colors the logo really has and
    choose a reasonable K for quantization.

    This avoids the ELON issue where 3 non-white colors get merged into
    one because K was capped too low and most palette slots were used
    for slightly different whites.
    """
    # Small adaptive palette view of the image
    pal_img = im.convert("P", palette=Image.Palette.ADAPTIVE, colors=16)
    colors = pal_img.getcolors(maxcolors=256) or []
    if not colors:
        return 3

    pal = pal_img.getpalette()
    bg = _sample_bg_color(im)
    # anything reasonably far from the bg is "non-background"
    bg_thresh_sq = 20 * 20

    non_bg_count = 0
    for _, idx in colors:
        r, g, b = pal[idx * 3 : idx * 3 + 3]
        if _color_dist((r, g, b), bg) > bg_thresh_sq:
            non_bg_count += 1

    # Map non-bg color count to a palette size; clamp to [3, max_k]
    if non_bg_count <= 1:
        k = 3  # one logo color + background
    elif non_bg_count == 2:
        k = 4
    elif non_bg_count == 3:
        k = 5
    else:
        k = max_k

    return max(3, min(k, max_k))


# =========================
# Main pipeline
# =========================


def vectorize_logo_safe_to_svg_bytes(image_bytes: bytes) -> bytes:
    """
    Two-pass “logo-safe” vectorization:
      1) Fills with VTracer
      2) Strokes from darkest color with Potrace (stroke only, no fill)
      3) Compose stroke group on top of fill SVG
    """
    # 0) Load & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)      # kills alpha halos
    im = _upsample_2x(im)               # more pixels → cleaner curves

    # 1) Strong dehalo to knock out fringe against white
    im = _dehalo_to_white(im, bg=None, dist_thresh_sq=11 * 11)

    # 2) Estimate palette size based on non-background colors.
    #    This prevents multi-color logos (like ELON) from collapsing
    #    into a single silhouette color.
    k = _estimate_logo_palette_size(im, max_k=6)

    # 3) Quantize (no dithering)
    im_q = _quantize_no_dither(im, k)

    # 4) Gentle regularization and snap-to-palette
    im_smooth = _gentle_regularize(im_q)
    im_final = _reindex_to_palette(im_smooth, k)

    # 4b) Second dehalo pass to murder remaining near-white fringe
    im_final = _dehalo_to_white(im_final, bg=None, dist_thresh_sq=9 * 9)

    # 5) Two-pass vectorization

    # 5A) Fills with VTracer
    png_path = _write_temp_image(im_final, ".png")
    fills_svg_fd, fills_svg_path = tempfile.mkstemp(suffix=".svg")
    os.close(fills_svg_fd)

    rc, _, err = _run(["vtracer", "-i", png_path, "-o", fills_svg_path])
    if rc != 0:
        raise RuntimeError(f"vtracer failed: {err.decode('utf-8', 'ignore')}")

    # 5B) Strokes (darkest color) with Potrace
    darkest = _get_darkest_palette_color(im_final)
    stroke_color_hex = _rgb_to_hex(darkest)

    mask = _make_mask_for_color(im_final, darkest)
    # Morphology for the stroke mask:
    # - One MinFilter(3) to remove isolated specks and tighten edges slightly
    # - One MaxFilter(3) to close tiny gaps / breaks without over-eroding thin strokes
    mask = mask.filter(ImageFilter.MinFilter(3))
    mask = mask.filter(ImageFilter.MaxFilter(3))

    # Potrace wants PBM (1-bit)
    pbm_path = _write_temp_image(mask, ".pbm")
    stroke_svg_fd, stroke_svg_path = tempfile.mkstemp(suffix=".svg")
    os.close(stroke_svg_fd)

    potrace_cmd = [
        "potrace",
        pbm_path,
        "--svg",
        "--turdsize",
        "4",                 # was 2; ignore smaller specks/rogue lines
        "--alphamax",
        "1.2",               # crisper corners
        "--opttolerance",
        "0.35",              # smoother where it can be
        "--turnpolicy",
        "minority",
        "-o",
        stroke_svg_path,
    ]
    rc, _, err = _run(potrace_cmd)
    if rc != 0:
        raise RuntimeError(f"potrace failed: {err.decode('utf-8', 'ignore')}")

    # 6) Compose SVG: use VTracer <svg> as base; import PATHS from Potrace on top
    fills_tree = ET.parse(fills_svg_path)
    fills_root = fills_tree.getroot()

    stroke_tree = ET.parse(stroke_svg_path)
    stroke_root = stroke_tree.getroot()

    def _tag(t: str) -> str:
        return t.split("}")[-1] if "}" in t else t

    # Create a stroke group with explicit stroke attributes (NO fill!)
    stroke_group = ET.Element(
        "g",
        attrib={
            "id": "stroke-layer",
            "fill": "none",
            "stroke": stroke_color_hex,
            "stroke-width": "2",
            "stroke-linejoin": "round",
            "stroke-linecap": "round",
        },
    )

    for el in stroke_root.iter():
        if _tag(el.tag) == "path":
            el.attrib.pop("fill", None)
            el.set("stroke", stroke_color_hex)
            el.set("stroke-width", "2")
            el.set("fill", "none")
            stroke_group.append(el)

    fills_root.append(stroke_group)

    # 7) Serialize to bytes
    svg_bytes = ET.tostring(fills_root, encoding="utf-8", method="xml")

    # cleanup temp files
    for p in (png_path, fills_svg_path, pbm_path, stroke_svg_path):
        try:
            os.remove(p)
        except OSError:
            pass

    return svg_bytes
