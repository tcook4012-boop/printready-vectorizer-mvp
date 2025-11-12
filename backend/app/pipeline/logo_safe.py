# app/pipeline/logo_safe.py
import io
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import Optional, Tuple

from PIL import Image, ImageFilter, ImageOps

# =========================
# Tunables (safe defaults)
# =========================
UPSAMPLE_FACTOR = 2                 # 2x keeps speed reasonable; raise to 3 for even smoother edges
DEHALO_RGB_THRESH = 9               # “near background” distance in RGB; higher = stronger dehalo (was 7)
NEAR_WHITE_THR = 232                # 0–255; snap anything brighter to pure white (helps flag stars)
NEAR_WHITE_GROW = 1                 # 0/1/2 px grow to solidify small white features
REG_MINMAX_SIZE = 3                 # morphology kernel for gentle regularization
REG_GAUSS_RADIUS = 0.7              # slight smoothing before re-quantize
UNSHARP = dict(radius=1.2, percent=160, threshold=2)  # subtle edge crisping

POTRACE = dict(
    turdsize="2",
    alphamax="1.15",                # lower = sharper corners; higher = rounder
    opttolerance="0.28",            # balance detail vs smooth
    turnpolicy="minority",
)
STROKE_WIDTH_PX = "2"               # visible outline for the darkest layer


# =========================
# Helpers
# =========================

def _to_srgb_rgba(im: Image.Image) -> Image.Image:
    if im.mode in ("P", "L"):
        im = im.convert("RGBA")
    elif im.mode == "RGB":
        im = im.convert("RGBA")
    elif im.mode == "LA":
        im = im.convert("RGBA")
    elif im.mode != "RGBA":
        im = im.convert("RGBA")
    return im

def _composite_over_white(im: Image.Image) -> Image.Image:
    if im.mode != "RGBA":
        return im.convert("RGB")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    out = Image.alpha_composite(bg, im)
    return out.convert("RGB")

def _sample_bg_color(im: Image.Image) -> Tuple[int, int, int]:
    w, h = im.size
    pts = [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]
    samples = [im.getpixel(p) for p in pts]
    counts = {}
    for c in samples:
        counts[c] = counts.get(c, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]

def _rgb_dist2(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    return (a[0] - b[0])**2 + (a[1] - b[1])**2 + (a[2] - b[2])**2

def _dehalo_to_white(im: Image.Image, bg=None, dist_thresh_sq: int = DEHALO_RGB_THRESH * DEHALO_RGB_THRESH) -> Image.Image:
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
            if _rgb_dist2(p, bg) <= dist_thresh_sq:
                mp[x, y] = 255

    # grow ~2 px, then paint those to white → removes background tint fringe
    mask = mask.filter(ImageFilter.MaxFilter(size=5))
    white = Image.new("RGB", im.size, (255, 255, 255))
    im.paste(white, mask=mask)
    return im

def _upsample(im: Image.Image, factor: int = UPSAMPLE_FACTOR) -> Image.Image:
    if factor <= 1:
        return im
    return im.resize((im.width * factor, im.height * factor), Image.Resampling.LANCZOS)

def _snap_near_white(im: Image.Image, thr: int = NEAR_WHITE_THR, grow_px: int = NEAR_WHITE_GROW) -> Image.Image:
    """
    Snap anything bright (>=thr) to pure white; lightly grow/shrink to lock small stars.
    Helpful for white stars sitting on a dark blue field.
    """
    # luminance channel for quick bright mask
    lum = im.convert("L")
    # threshold
    mask = lum.point(lambda v: 255 if v >= thr else 0, mode="L")
    if grow_px > 0:
        # close: grow then shrink to keep sharp corners while filling pinholes
        for _ in range(grow_px):
            mask = mask.filter(ImageFilter.MaxFilter(3))
        for _ in range(grow_px):
            mask = mask.filter(ImageFilter.MinFilter(3))
    white = Image.new("RGB", im.size, (255, 255, 255))
    out = im.copy()
    out.paste(white, mask=mask)
    return out

def _quantize_no_dither(im: Image.Image, k: int) -> Image.Image:
    q = im.quantize(colors=k, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    return q.convert("RGB")

def _gentle_regularize(im: Image.Image) -> Image.Image:
    im = im.filter(ImageFilter.MinFilter(REG_MINMAX_SIZE))
    im = im.filter(ImageFilter.MaxFilter(REG_MINMAX_SIZE))
    im = im.filter(ImageFilter.GaussianBlur(radius=REG_GAUSS_RADIUS))
    return im

def _unsharp(im: Image.Image) -> Image.Image:
    return im.filter(ImageFilter.UnsharpMask(**UNSHARP))

def _reindex_to_palette(im: Image.Image, k: int) -> Image.Image:
    return _quantize_no_dither(im, k)

def _get_darkest_palette_color(pal_img: Image.Image) -> Tuple[int, int, int]:
    if pal_img.mode != "P":
        tmp = pal_img.quantize(colors=min(16, (pal_img.getcolors() or [None]*8).__len__()),
                               method=Image.MEDIANCUT,
                               dither=Image.Dither.NONE)
        pal_img = tmp
    pal = pal_img.getpalette()
    used = set([idx for _, idx in (pal_img.getcolors(maxcolors=256) or [])])
    darkest, min_y = (0, 0, 0), 1e9
    for idx in used:
        r, g, b = pal[idx*3: idx*3+3]
        y = 0.2126*r + 0.7152*g + 0.0722*b
        if y < min_y:
            min_y = y
            darkest = (r, g, b)
    return darkest

def _rgb_to_hex(c: Tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*c)

def _mask_for_color(im_rgb: Image.Image, target: Tuple[int, int, int]) -> Image.Image:
    w, h = im_rgb.size
    mask = Image.new("1", (w, h), 0)
    mp = mask.load()
    px = im_rgb.load()
    for y in range(h):
        for x in range(w):
            if px[x, y] == target:
                mp[x, y] = 1
    return mask

def _write_temp(im: Image.Image, suffix: str) -> str:
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

def vectorize_logo_safe_to_svg_bytes(image_bytes: bytes, auto_k_min=4, auto_k_max=6) -> bytes:
    """
    “Logo-safe” two-pass vectorization:
      • Prep: de-halo, snap near-white (stars), gentle regularize, unsharp
      • Fills: VTracer
      • Strokes: Potrace on darkest color mask
      • Compose: stroke group on top of fills
    """
    # 0) Load & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)
    im = _upsample(im, UPSAMPLE_FACTOR)

    # 1) Clean edges: de-halo + snap white features (stars/white text)
    im = _dehalo_to_white(im, bg=None)                                # stronger fringe removal
    im = _snap_near_white(im, thr=NEAR_WHITE_THR, grow_px=NEAR_WHITE_GROW)

    # 2) Auto-K based on rough unique color count
    approx_unique = len(im.convert("P", palette=Image.Palette.ADAPTIVE, colors=16).getcolors() or [])
    if approx_unique <= 3:
        k = 3
    elif approx_unique >= auto_k_max:
        k = auto_k_max
    else:
        k = max(auto_k_min, min(auto_k_max, approx_unique))

    # 3) Quantize → regularize → re-quantize → unsharp for crispness
    im_q = _quantize_no_dither(im, k)
    im_smooth = _gentle_regularize(im_q)
    im_final = _reindex_to_palette(im_smooth, k)
    im_final = _unsharp(im_final)

    # 4) Vectorize fills (VTracer)
    png_path = _write_temp(im_final, ".png")
    fills_svg_fd, fills_svg_path = tempfile.mkstemp(suffix=".svg"); os.close(fills_svg_fd)
    rc, _, err = _run(["vtracer", "-i", png_path, "-o", fills_svg_path])
    if rc != 0:
        raise RuntimeError(f"vtracer failed: {err.decode('utf-8', 'ignore')}")

    # 5) Vectorize darkest strokes (Potrace)
    darkest = _get_darkest_palette_color(im_final)
    stroke_hex = _rgb_to_hex(darkest)
    mask = _mask_for_color(im_final, darkest)
    # tighten a touch so outlines don’t bloat
    mask = mask.filter(ImageFilter.MinFilter(3))

    pbm_path = _write_temp(mask, ".pbm")
    stroke_svg_fd, stroke_svg_path = tempfile.mkstemp(suffix=".svg"); os.close(stroke_svg_fd)

    potrace_cmd = [
        "potrace",
        pbm_path,
        "--svg",
        "--turdsize", POTRACE["turdsize"],
        "--alphamax", POTRACE["alphamax"],
        "--opttolerance", POTRACE["opttolerance"],
        "--turnpolicy", POTRACE["turnpolicy"],
        "-o", stroke_svg_path,
    ]
    rc, _, err = _run(potrace_cmd)
    if rc != 0:
        raise RuntimeError(f"potrace failed: {err.decode('utf-8', 'ignore')}")

    # 6) Compose: import Potrace paths as stroked group over the VTracer SVG
    fills_tree = ET.parse(fills_svg_path)
    fills_root = fills_tree.getroot()
    stroke_tree = ET.parse(stroke_svg_path)
    stroke_root = stroke_tree.getroot()

    def _tag(t: str) -> str:
        return t.split("}")[-1] if "}" in t else t

    g = ET.Element(
        "g",
        attrib={
            "id": "stroke-layer",
            "fill": "none",
            "stroke": stroke_hex,
            "stroke-width": STROKE_WIDTH_PX,
            "stroke-linejoin": "round",
            "stroke-linecap": "round",
        },
    )
    for el in stroke_root.iter():
        if _tag(el.tag) == "path":
            el.attrib.pop("fill", None)
            el.set("stroke", stroke_hex)
            el.set("stroke-width", STROKE_WIDTH_PX)
            el.set("fill", "none")
            g.append(el)

    fills_root.append(g)
    svg_bytes = ET.tostring(fills_root, encoding="utf-8", method="xml")

    # cleanup
    for p in (png_path, fills_svg_path, pbm_path, stroke_svg_path):
        try:
            os.remove(p)
        except OSError:
            pass

    return svg_bytes
