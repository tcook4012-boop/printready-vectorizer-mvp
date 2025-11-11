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

def _white_sweep(im: Image.Image, thresh: int = 248) -> Image.Image:
    """
    Push very-near-white pixels to pure white. Helps remove faint halos
    left over after compositing + dehalo.
    """
    im = im.convert("RGB")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r >= thresh and g >= thresh and b >= thresh:
                px[x, y] = (255, 255, 255)
    return im

def _dehalo_to_white(im: Image.Image, bg=None, dist_thresh_sq: int = 10 * 10):
    """
    Replace pixels close to the background with pure white, then grow by ~2px.
    Using slightly stronger default than before to shrink hazy borders.
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

    # Grow mask ~2px and apply
    mask = mask.filter(ImageFilter.MaxFilter(size=5))
    white = Image.new("RGB", im.size, (255, 255, 255))
    im.paste(white, mask=mask)
    return im

def _upsample(im: Image.Image, factor: int = 3) -> Image.Image:
    """Higher upsample → cleaner curves and crisper small shapes (stars, serifs)."""
    return im.resize((im.width * factor, im.height * factor), Image.Resampling.LANCZOS)

def _quantize_no_dither(im: Image.Image, k: int) -> Image.Image:
    """Median cut to k colors, no dithering."""
    q = im.quantize(colors=k, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    return q.convert("RGB")

def _gentle_regularize(im: Image.Image, blur_radius: float = 0.6) -> Image.Image:
    """
    Light morphological clean-up:
    Min -> Max (size=3) to close tiny gaps, then small blur to smooth edges.
    """
    im = im.filter(ImageFilter.MinFilter(3))
    im = im.filter(ImageFilter.MaxFilter(3))
    im = im.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    return im

def _light_unsharp(im: Image.Image, radius: float = 1.2, amount: float = 0.25) -> Image.Image:
    """
    A very light unsharp mask: im + amount*(im - blur). Negative blend keeps it simple with PIL.
    """
    blur = im.filter(ImageFilter.GaussianBlur(radius))
    # 1.0*im - amount*blur  (implemented via blend with negative alpha)
    return Image.blend(im, blur, -amount)

def _reindex_to_palette(im: Image.Image, k: int) -> Image.Image:
    """Snap smoothed image back to an exact K-color palette."""
    return _quantize_no_dither(im, k)

def _get_darkest_palette_color(pal_img: Image.Image) -> Tuple[int, int, int]:
    """Find the darkest color (by luma) among used palette entries."""
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

# ---- SVG post-process: hide antialias seams between adjacent fills ----
def _apply_fill_stroke_hack(svg_root: ET.Element, stroke_width: str = "0.3"):
    """
    Adds a tiny stroke matching each path's fill and sets crisp rendering hints.
    This mitigates hairline seams some viewers show between touching paths.
    """
    # root rendering hints
    style_root = svg_root.get("style", "")
    extra = "shape-rendering:crispEdges;paint-order:stroke fill;vector-effect:non-scaling-stroke;"
    svg_root.set("style", (style_root + ";" + extra).strip(";"))

    def tag_name(t: str) -> str:
        return t.split("}")[-1] if "}" in t else t

    for el in svg_root.iter():
        if tag_name(el.tag) == "path":
            fill = el.get("fill")
            if fill and fill.lower() != "none":
                el.set("stroke", fill)
                el.set("stroke-width", stroke_width)
                # round joins help hide micro-gaps
                el.set("stroke-linejoin", "round")

# =========================
# Main pipeline
# =========================

def vectorize_logo_safe_to_svg_bytes(image_bytes: bytes, auto_k_min=4, auto_k_max=6) -> bytes:
    """
    Two-pass “logo-safe” vectorization:
      1) Fills with VTracer
      2) Strokes from darkest color with Potrace (stroke only, no fill)
      3) Compose stroke group on top of fill SVG
    """
    # 0) Load & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)          # kills alpha halos
    im = _white_sweep(im, thresh=248)       # push near-white to white
    im = _upsample(im, factor=3)            # more pixels → cleaner curves

    # (Optional) a touch of unsharp for tiny details like stars
    im = _light_unsharp(im, radius=1.0, amount=0.18)

    # 1) Dehalo background (a bit stronger)
    im = _dehalo_to_white(im, bg=None, dist_thresh_sq=10 * 10)

    # 2) Auto K selection: rough heuristic from unique colors
    approx_unique = len(im.convert("P", palette=Image.Palette.ADAPTIVE, colors=16).getcolors() or [])
    if approx_unique <= 3:
        k = 3
    elif approx_unique >= auto_k_max:
        k = auto_k_max
    else:
        k = max(auto_k_min, min(auto_k_max, approx_unique))

    # 3) Quantize (no dithering)
    im_q = _quantize_no_dither(im, k)

    # 4) Gentle regularization and snap-to-palette
    im_smooth = _gentle_regularize(im_q, blur_radius=0.55)  # slightly tighter than before
    im_final = _reindex_to_palette(im_smooth, k)

    # 5) Two-pass vectorization

    # 5A) Fills with VTracer (defaults are okay for v0.6.x)
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
    # tighten so outlines don't bloat or leak halo color
    mask = mask.filter(ImageFilter.MinFilter(3))
    mask = mask.filter(ImageFilter.MinFilter(3))  # extra erosion

    pbm_path = _write_temp_image(mask, ".pbm")
    stroke_svg_fd, stroke_svg_path = tempfile.mkstemp(suffix=".svg")
    os.close(stroke_svg_fd)

    # A bit crisper corners, but still smooth; higher turdsize removes stray lines/specks
    potrace_cmd = [
        "potrace",
        pbm_path,
        "--svg",
        "--turdsize", "3",          # ↑ from 2 → fewer tiny artifacts
        "--alphamax", "1.08",       # ↓ from 1.2–1.4 → sharper corners
        "--opttolerance", "0.30",   # moderate fit quality
        "--turnpolicy", "minority",
        "-o", stroke_svg_path,
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

    # Fill seam fix: tiny same-color stroke on all fill paths
    _apply_fill_stroke_hack(fills_root, stroke_width="0.3")

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
            "vector-effect": "non-scaling-stroke",
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

    # cleanup
    for p in (png_path, fills_svg_path, pbm_path, stroke_svg_path):
        try:
            os.remove(p)
        except OSError:
            pass

    return svg_bytes
