# app/pipeline/logo_safe.py
import io
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import Optional, Tuple

from PIL import Image, ImageFilter

# Try OpenCV for edge-preserving smoothing; fall back gracefully.
try:
    import cv2  # type: ignore
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False


# ============================================================
#  T U N I N G   D I A L S   (easy to edit later)
#  (Line numbers shown for quick reference in your editor.)
# ============================================================

UPSCALE_FACTOR = 3               # LINE: 24  (was 2) – more pixels => smoother vectors
DEHALO_RGB_DIST = 12             # LINE: 25  (was 9) – “2 bumps” stronger haze removal
DEHALO_GROW_PX = 3               # LINE: 26  (was ~2) – grow near-bg mask this many pixels

BILATERAL_D = 7                  # LINE: 28  OpenCV bilateral params (edge-preserving)
BILATERAL_SIGMA_COLOR = 50       # LINE: 29
BILATERAL_SIGMA_SPACE = 50       # LINE: 30

GAUSS_AFTER_BILATERAL = 0.8      # LINE: 32  small post-smooth blur if cv2 missing or to blend

REG_MIN_SIZE = 3                 # LINE: 34  morphology window sizes
REG_MAX_SIZE = 3
REG_GAUSS = 1.1                  # LINE: 36  a touch more smoothing (was 0.8)

REINDEX_PALETTE_MIN = 4          # LINE: 38  auto-K bounds
REINDEX_PALETTE_MAX = 6

# Potrace fitting: higher alphamax & opttolerance => rounder/cleaner curves
POTRACE_TURDSIZE = 2             # LINE: 42
POTRACE_ALPHAMAX = 1.6           # LINE: 43  (was 1.2/1.4)
POTRACE_OPTTOL = 0.6             # LINE: 44  (was 0.35/0.2)
POTRACE_TURNPOL = "minority"     # LINE: 45

STROKE_WIDTH_PX = "2"            # LINE: 47  SVG stroke width for outline group


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

def _dehalo_to_white(im: Image.Image, bg=None, dist_thresh: int = DEHALO_RGB_DIST, grow_px: int = DEHALO_GROW_PX):
    """
    Replace pixels near the background with pure white, then grow by ~N px.
    Uses simple RGB distance; fast and robust.
    """
    im = im.copy()
    w, h = im.size
    if bg is None:
        bg = _sample_bg_color(im)

    px = im.load()
    mask = Image.new("L", im.size, 0)
    mp = mask.load()
    thresh_sq = dist_thresh * dist_thresh
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if _color_dist(p, bg) <= thresh_sq:
                mp[x, y] = 255

    # grow mask by ~grow_px
    # filter size must be odd and roughly (2*grow_px + 1)
    k = max(1, 2 * grow_px + 1)
    if k % 2 == 0:  # ensure odd
        k += 1
    mask = mask.filter(ImageFilter.MaxFilter(size=k))

    white = Image.new("RGB", im.size, (255, 255, 255))
    im.paste(white, mask=mask)
    return im

def _upsample(im: Image.Image, factor: int = UPSCALE_FACTOR) -> Image.Image:
    if factor <= 1:
        return im
    return im.resize((im.width * factor, im.height * factor), Image.Resampling.LANCZOS)

def _edge_preserve_smooth(im: Image.Image) -> Image.Image:
    """
    Edge-preserving smoothing to reduce jaggies on diagonals/stars without
    blurring edges into the background. Uses OpenCV bilateral if available.
    """
    if HAS_CV2:
        # PIL RGB -> BGR array
        arr = cv2.cvtColor(
            cv2.UMat.fromArray(
                __import__("numpy").asarray(im).astype("uint8")
            ).get(),
            cv2.COLOR_RGB2BGR,
        )
        arr = cv2.bilateralFilter(arr, d=BILATERAL_D,
                                  sigmaColor=BILATERAL_SIGMA_COLOR,
                                  sigmaSpace=BILATERAL_SIGMA_SPACE)
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        out = Image.fromarray(arr)
        # Small gaussian to blend residual speckle
        if GAUSS_AFTER_BILATERAL > 0:
            out = out.filter(ImageFilter.GaussianBlur(radius=GAUSS_AFTER_BILATERAL))
        return out
    else:
        # Fallback: slightly stronger gaussian
        return im.filter(ImageFilter.GaussianBlur(radius=max(1.2, GAUSS_AFTER_BILATERAL)))

def _quantize_no_dither(im: Image.Image, k: int) -> Image.Image:
    """Median cut to k colors, no dithering."""
    q = im.quantize(colors=k, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    return q.convert("RGB")

def _gentle_regularize(im: Image.Image) -> Image.Image:
    """
    Light morphological clean-up:
    Min -> Max (size=REG_*) to close tiny gaps, then small blur to smooth edges.
    """
    im = im.filter(ImageFilter.MinFilter(REG_MIN_SIZE))
    im = im.filter(ImageFilter.MaxFilter(REG_MAX_SIZE))
    im = im.filter(ImageFilter.GaussianBlur(radius=REG_GAUSS))
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


# =========================
# Main pipeline
# =========================

def vectorize_logo_safe_to_svg_bytes(image_bytes: bytes,
                                     auto_k_min: int = REINDEX_PALETTE_MIN,
                                     auto_k_max: int = REINDEX_PALETTE_MAX) -> bytes:
    """
    Two-pass “logo-safe” vectorization:
      1) Fills with VTracer
      2) Strokes from darkest color with Potrace (stroke only, no fill)
      3) Compose stroke group on top of fill SVG
    """

    # 0) Load & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)      # kill alpha halos
    im = _upsample(im, UPSCALE_FACTOR)  # more pixels => smoother vectors

    # 1) Stronger dehalo near the sampled background
    im = _dehalo_to_white(im, bg=None, dist_thresh=DEHALO_RGB_DIST, grow_px=DEHALO_GROW_PX)

    # 1.5) Edge-preserving smoothing for diagonals/stars
    im = _edge_preserve_smooth(im)

    # 2) Auto K selection
    approx_unique = len(im.convert("P", palette=Image.Palette.ADAPTIVE, colors=16).getcolors() or [])
    if approx_unique <= 3:
        k = 3
    elif approx_unique >= auto_k_max:
        k = auto_k_max
    else:
        k = max(auto_k_min, min(auto_k_max, approx_unique))

    # 3) Quantize (no dithering)
    im_q = _quantize_no_dither(im, k)

    # 4) Regularize edges and snap to palette
    im_smooth = _gentle_regularize(im_q)
    im_final = _reindex_to_palette(im_smooth, k)

    # 5) Two-pass vectorization

    # 5A) Fills with VTracer
    png_path = _write_temp_image(im_final, ".png")
    fills_svg_fd, fills_svg_path = tempfile.mkstemp(suffix=".svg")
    os.close(fills_svg_fd)

    # Keep args minimal/robust across vtracer 0.6.x
    rc, _, err = _run(["vtracer", "-i", png_path, "-o", fills_svg_path])
    if rc != 0:
        raise RuntimeError(f"vtracer failed: {err.decode('utf-8', 'ignore')}")

    # 5B) Strokes (darkest color) with Potrace
    darkest = _get_darkest_palette_color(im_final)
    stroke_color_hex = _rgb_to_hex(darkest)

    mask = _make_mask_for_color(im_final, darkest)
    # A bit more erosion keeps outlines tight and reduces residual haze
    mask = mask.filter(ImageFilter.MinFilter(3))
    mask = mask.filter(ImageFilter.MinFilter(3))  # two passes

    pbm_path = _write_temp_image(mask, ".pbm")
    stroke_svg_fd, stroke_svg_path = tempfile.mkstemp(suffix=".svg")
    os.close(stroke_svg_fd)

    potrace_cmd = [
        "potrace",
        pbm_path,
        "--svg",
        "--turdsize", str(POTRACE_TURDSIZE),
        "--alphamax", str(POTRACE_ALPHAMAX),
        "--opttolerance", str(POTRACE_OPTTOL),
        "--turnpolicy", POTRACE_TURNPOL,
        "-o", stroke_svg_path,
    ]
    rc, _, err = _run(potrace_cmd)
    if rc != 0:
        raise RuntimeError(f"potrace failed: {err.decode('utf-8', 'ignore')}")

    # 6) Compose SVG: VTracer <svg> base + Potrace paths on top
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
            "stroke-width": STROKE_WIDTH_PX,
            "stroke-linejoin": "round",
            "stroke-linecap": "round",
        },
    )

    for el in stroke_root.iter():
        if _tag(el.tag) == "path":
            el.attrib.pop("fill", None)
            el.set("stroke", stroke_color_hex)
            el.set("stroke-width", STROKE_WIDTH_PX)
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
