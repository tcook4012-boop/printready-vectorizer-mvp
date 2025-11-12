# app/pipeline/logo_safe.py
import io
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import Optional, Tuple

from PIL import Image, ImageFilter

# Try OpenCV for edge-preserving smoothing; fall back gracefully
try:
    import cv2  # type: ignore
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

import numpy as np  # required for OpenCV array conversions


# ==============================
# CONFIG / TUNABLE PARAMETERS
# ==============================
UPSCALE_FACTOR = 3
DEHALO_RGB_DIST = 12
DEHALO_GROW_PX = 3

BILATERAL_D = 7
BILATERAL_SIGMA_COLOR = 50
BILATERAL_SIGMA_SPACE = 50
GAUSS_AFTER_BILATERAL = 0.8

REG_MIN_SIZE = 3
REG_MAX_SIZE = 3
REG_GAUSS = 1.1

REINDEX_PALETTE_MIN = 4
REINDEX_PALETTE_MAX = 6

POTRACE_TURDSIZE = 2
POTRACE_ALPHAMAX = 1.6
POTRACE_OPTTOL = 0.6
POTRACE_TURNPOL = "minority"

STROKE_WIDTH_PX = "2"


# ==============================
# IMAGE HELPERS
# ==============================
def _to_srgb_rgba(im: Image.Image) -> Image.Image:
    if im.mode in ("P", "L"):
        im = im.convert("RGBA")
    elif im.mode in ("RGB", "LA"):
        im = im.convert("RGBA")
    return im


def _composite_over_white(im: Image.Image) -> Image.Image:
    if im.mode != "RGBA":
        return im.convert("RGB")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB")


def _sample_bg_color(im: Image.Image) -> Tuple[int, int, int]:
    w, h = im.size
    pts = [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]
    samples = [im.getpixel(p) for p in pts]
    return max(set(samples), key=samples.count)


def _color_dist(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _dehalo_to_white(im: Image.Image, bg=None, dist_thresh: int = DEHALO_RGB_DIST, grow_px: int = DEHALO_GROW_PX):
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
            if _color_dist(px[x, y], bg) <= thresh_sq:
                mp[x, y] = 255

    k = max(1, 2 * grow_px + 1)
    if k % 2 == 0:
        k += 1
    mask = mask.filter(ImageFilter.MaxFilter(size=k))
    white = Image.new("RGB", im.size, (255, 255, 255))
    im.paste(white, mask=mask)
    return im


def _upsample(im: Image.Image, factor: int = UPSCALE_FACTOR) -> Image.Image:
    return im.resize((im.width * factor, im.height * factor), Image.Resampling.LANCZOS)


def _edge_preserve_smooth(im: Image.Image) -> Image.Image:
    """Edge-preserving smoothing to reduce jaggies without blurring edges."""
    if not HAS_CV2:
        return im.filter(ImageFilter.GaussianBlur(radius=max(1.2, GAUSS_AFTER_BILATERAL)))

    try:
        arr = np.array(im)
        arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        arr_out = cv2.bilateralFilter(
            arr_bgr,
            d=BILATERAL_D,
            sigmaColor=BILATERAL_SIGMA_COLOR,
            sigmaSpace=BILATERAL_SIGMA_SPACE,
        )
        arr_rgb = cv2.cvtColor(arr_out, cv2.COLOR_BGR2RGB)
        out = Image.fromarray(arr_rgb)
        if GAUSS_AFTER_BILATERAL > 0:
            out = out.filter(ImageFilter.GaussianBlur(radius=GAUSS_AFTER_BILATERAL))
        return out
    except Exception:
        return im.filter(ImageFilter.GaussianBlur(radius=max(1.2, GAUSS_AFTER_BILATERAL)))


def _quantize_no_dither(im: Image.Image, k: int) -> Image.Image:
    q = im.quantize(colors=k, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    return q.convert("RGB")


def _gentle_regularize(im: Image.Image) -> Image.Image:
    im = im.filter(ImageFilter.MinFilter(REG_MIN_SIZE))
    im = im.filter(ImageFilter.MaxFilter(REG_MAX_SIZE))
    im = im.filter(ImageFilter.GaussianBlur(radius=REG_GAUSS))
    return im


def _reindex_to_palette(im: Image.Image, k: int) -> Image.Image:
    return _quantize_no_dither(im, k)


def _get_darkest_palette_color(pal_img: Image.Image) -> Tuple[int, int, int]:
    if pal_img.mode != "P":
        pal_img = pal_img.quantize(colors=8, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    pal = pal_img.getpalette()
    used = {idx for _, idx in pal_img.getcolors(maxcolors=256) or []}
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


# ==============================
# MAIN PIPELINE
# ==============================
def vectorize_logo_safe_to_svg_bytes(image_bytes: bytes,
                                     auto_k_min: int = REINDEX_PALETTE_MIN,
                                     auto_k_max: int = REINDEX_PALETTE_MAX) -> bytes:
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)
    im = _upsample(im, UPSCALE_FACTOR)
    im = _dehalo_to_white(im)
    im = _edge_preserve_smooth(im)

    approx_unique = len(im.convert("P", palette=Image.Palette.ADAPTIVE, colors=16).getcolors() or [])
    if approx_unique <= 3:
        k = 3
    elif approx_unique >= auto_k_max:
        k = auto_k_max
    else:
        k = max(auto_k_min, min(auto_k_max, approx_unique))

    im_q = _quantize_no_dither(im, k)
    im_smooth = _gentle_regularize(im_q)
    im_final = _reindex_to_palette(im_smooth, k)

    png_path = _write_temp_image(im_final, ".png")
    fills_svg_fd, fills_svg_path = tempfile.mkstemp(suffix=".svg")
    os.close(fills_svg_fd)

    rc, _, err = _run(["vtracer", "-i", png_path, "-o", fills_svg_path])
    if rc != 0:
        raise RuntimeError(f"vtracer failed: {err.decode('utf-8', 'ignore')}")

    darkest = _get_darkest_palette_color(im_final)
    stroke_color_hex = _rgb_to_hex(darkest)

    mask = _make_mask_for_color(im_final, darkest)
    mask = mask.filter(ImageFilter.MinFilter(3))
    mask = mask.filter(ImageFilter.MinFilter(3))

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
    svg_bytes = ET.tostring(fills_root, encoding="utf-8", method="xml")

    for p in (png_path, fills_svg_path, pbm_path, stroke_svg_path):
        try:
            os.remove(p)
        except OSError:
            pass

    return svg_bytes
