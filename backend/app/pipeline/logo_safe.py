# app/pipeline/logo_safe.py
import io
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import Optional, Tuple

from PIL import Image, ImageFilter

# ============================================================
# Helpers
# ============================================================

def _to_srgb_rgba(im: Image.Image) -> Image.Image:
    """Normalize to RGBA (sRGB-ish)."""
    if im.mode in ("P", "L", "RGB", "LA"):
        im = im.convert("RGBA") if im.mode != "RGBA" else im
    elif im.mode != "RGBA":
        im = im.convert("RGBA")
    return im

def _composite_over_white(im: Image.Image) -> Image.Image:
    """Flatten alpha over white; removes semi-transparent edge contamination."""
    if im.mode != "RGBA":
        return im.convert("RGB")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    out = Image.alpha_composite(bg, im)
    return out.convert("RGB")

def _force_white_edges(im: Image.Image) -> Image.Image:
    """
    Hard-threshold pixels that are already very close to white.
    This kills the purple/gray 'haze' that shows up around edges.
    """
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r > 245 and g > 245 and b > 245:
                px[x, y] = (255, 255, 255)
    return im

def _sample_bg_color(im: Image.Image) -> Tuple[int, int, int]:
    """Modal of 4 corners to guess the background color."""
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

def _dehalo_to_white(im: Image.Image, bg=None, dist_thresh_sq: int = 10 * 10):
    """
    Replace pixels close to background with pure white and grow the white region.
    Raising the threshold + radius is what removes the residual haze.
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
            if _color_dist(px[x, y], bg) <= dist_thresh_sq:
                mp[x, y] = 255

    # Grow the white mask ~3px to swallow soft fringe pixels
    mask = mask.filter(ImageFilter.MaxFilter(size=7))
    white = Image.new("RGB", im.size, (255, 255, 255))
    im.paste(white, mask=mask)
    return im

def _upsample_2x(im: Image.Image) -> Image.Image:
    """More pixels → smoother curves post-vectorization."""
    return im.resize((im.width * 2, im.height * 2), Image.Resampling.LANCZOS)

def _smart_edge_smooth(im: Image.Image) -> Image.Image:
    """
    Curvature-aware smoothing:
    bilateral filter preserves edges; light Gaussian removes pixel stair-steps.
    """
    import numpy as np
    import cv2

    arr = np.array(im)                      # RGB
    arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    # d=5, sigmaColor/Space moderate to keep letter corners
    out_bgr = cv2.bilateralFilter(arr_bgr, d=5, sigmaColor=40, sigmaSpace=40)
    out_bgr = cv2.GaussianBlur(out_bgr, (3, 3), 0.6)
    out_rgb = cv2.cvtColor(out_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(out_rgb)

def _quantize_no_dither(im: Image.Image, k: int) -> Image.Image:
    """Median cut to k colors without dithering."""
    q = im.quantize(colors=k, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    return q.convert("RGB")

def _gentle_regularize(im: Image.Image) -> Image.Image:
    """
    Light morphological clean-up. Small Min/Max closes pinholes; mild blur smooths edges.
    """
    im = im.filter(ImageFilter.MinFilter(3))
    im = im.filter(ImageFilter.MaxFilter(3))
    im = im.filter(ImageFilter.GaussianBlur(radius=0.6))
    return im

def _reindex_to_palette(im: Image.Image, k: int) -> Image.Image:
    """Snap smoothed image back to an exact K-color palette."""
    return _quantize_no_dither(im, k)

def _get_darkest_palette_color(pal_img: Image.Image) -> Tuple[int, int, int]:
    """Find darkest used palette entry (by luma)."""
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


# ============================================================
# Main pipeline
# ============================================================

def vectorize_logo_safe_to_svg_bytes(image_bytes: bytes, auto_k_min=4, auto_k_max=6) -> bytes:
    """
    Two-pass “logo-safe” pipeline:
      1) Pre-clean (dehalo + curvature-aware smooth) → Quantize (no dither)
      2) VTracer for fills
      3) Potrace for darkest-color outlines (detail-preserving settings)
      4) Compose: <paths> from Potrace on top of VTracer <svg>
    """
    # 0) Load & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)  # remove alpha
    im = _force_white_edges(im)     # kill fringe haze
    im = _upsample_2x(im)           # more pixels → smoother result

    # 1) Dehalo + curvature-aware smoothing
    im = _dehalo_to_white(im, bg=None, dist_thresh_sq=10 * 10)  # stronger than before
    im = _smart_edge_smooth(im)

    # 2) Auto-K heuristic for palette size
    approx_unique = len(im.convert("P", palette=Image.Palette.ADAPTIVE, colors=16).getcolors() or [])
    if approx_unique <= 3:
        k = 3
    elif approx_unique >= auto_k_max:
        k = auto_k_max
    else:
        k = max(auto_k_min, min(auto_k_max, approx_unique))

    # 3) Quantize and lightly regularize, then snap to palette again
    im_q = _quantize_no_dither(im, k)
    im_smooth = _gentle_regularize(im_q)
    im_final = _reindex_to_palette(im_smooth, k)

    # 4) Fills with VTracer
    png_path = _write_temp_image(im_final, ".png")
    fills_svg_fd, fills_svg_path = tempfile.mkstemp(suffix=".svg"); os.close(fills_svg_fd)

    rc, _, err = _run(["vtracer", "-i", png_path, "-o", fills_svg_path])
    if rc != 0:
        raise RuntimeError(f"vtracer failed: {err.decode('utf-8', 'ignore')}")

    # 5) Strokes (darkest color) with Potrace — small-detail friendly
    darkest = _get_darkest_palette_color(im_final)
    stroke_color_hex = _rgb_to_hex(darkest)

    mask = _make_mask_for_color(im_final, darkest)
    # Slight erosion to avoid “bold” outlines; run once (can run twice if needed)
    mask = mask.filter(ImageFilter.MinFilter(3))

    pbm_path = _write_temp_image(mask, ".pbm")
    stroke_svg_fd, stroke_svg_path = tempfile.mkstemp(suffix=".svg"); os.close(stroke_svg_fd)

    potrace_cmd = [
        "potrace",
        pbm_path,
        "--svg",
        "--turdsize", "1",        # preserve tiny shapes (stars, counters)
        "--alphamax", "1.0",      # lower = crisper corners, less rounding
        "--opttolerance", "0.4",  # balance smoothness & fidelity
        "--turnpolicy", "minority",
        "-o", stroke_svg_path,
    ]
    rc, _, err = _run(potrace_cmd)
    if rc != 0:
        raise RuntimeError(f"potrace failed: {err.decode('utf-8', 'ignore')}")

    # 6) Compose Potrace paths on top of VTracer SVG
    fills_tree = ET.parse(fills_svg_path)
    fills_root = fills_tree.getroot()

    stroke_tree = ET.parse(stroke_svg_path)
    stroke_root = stroke_tree.getroot()

    def _tag(t: str) -> str:
        return t.split("}")[-1] if "}" in t else t

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

    # Cleanup
    for p in (png_path, fills_svg_path, pbm_path, stroke_svg_path):
        try:
            os.remove(p)
        except OSError:
            pass

    return svg_bytes
