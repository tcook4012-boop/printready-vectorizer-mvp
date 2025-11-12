# app/pipeline/logo_safe.py
import io
import os
import gc
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import Optional, Tuple

from PIL import Image, ImageFilter

# -------- optional, fast edge-preserving smoothing --------
try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

# ==============================
# MEMORY / QUALITY GUARDRAILS
# ==============================
# Keep working images under ~12–16 MP on 512 MB instances
MAX_WORK_PIXELS = int(14e6)   # cap W*H after we resize
MAX_SIDE_PX     = 3200        # never exceed this on either dimension
MAX_UPLOAD_MB   = 20          # safety; actual check belongs in main.py if desired

# Baseline vectorization settings
DEHALO_RGB_DIST     = 12
DEHALO_GROW_PX      = 3
REG_MIN_SIZE        = 3
REG_MAX_SIZE        = 3
REG_GAUSS           = 1.1
REINDEX_MIN_K       = 4
REINDEX_MAX_K       = 6

# OpenCV bilateral defaults (used only on moderate sizes)
BILATERAL_D             = 7
BILATERAL_SIGMA_COLOR   = 50
BILATERAL_SIGMA_SPACE   = 50
GAUSS_AFTER_BILATERAL   = 0.8

# Potrace params
POTRACE_TURDSIZE   = 2
POTRACE_ALPHAMAX   = 1.6
POTRACE_OPTTOL     = 0.6
POTRACE_TURNPOL    = "minority"
STROKE_WIDTH_PX    = "2"


# ==============================
# UTILITIES
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
    pts = [(2, 2), (w-3, 2), (2, h-3), (w-3, h-3)]
    samples = [im.getpixel(p) for p in pts]
    return max(set(samples), key=samples.count)

def _color_dist(a: Tuple[int,int,int], b: Tuple[int,int,int]) -> int:
    return (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2

def _dehalo_to_white(im: Image.Image, bg=None, dist_thresh: int = DEHALO_RGB_DIST, grow_px: int = DEHALO_GROW_PX):
    im = im.copy()
    w, h = im.size
    if bg is None:
        bg = _sample_bg_color(im)

    thresh_sq = dist_thresh * dist_thresh
    src = im.load()
    mask = Image.new("L", im.size, 0); mp = mask.load()
    for y in range(h):
        for x in range(w):
            if _color_dist(src[x, y], bg) <= thresh_sq:
                mp[x, y] = 255

    k = max(1, 2*grow_px + 1)
    if k % 2 == 0:
        k += 1
    mask = mask.filter(ImageFilter.MaxFilter(size=k))

    white = Image.new("RGB", im.size, (255, 255, 255))
    im.paste(white, mask=mask)
    return im

def _cap_size(im: Image.Image) -> Image.Image:
    """Resize down to stay under MAX_WORK_PIXELS / MAX_SIDE_PX while preserving aspect."""
    w, h = im.size
    if w * h <= MAX_WORK_PIXELS and max(w, h) <= MAX_SIDE_PX:
        return im
    scale_by_pixels = (MAX_WORK_PIXELS / (w * h)) ** 0.5
    scale_by_side   = MAX_SIDE_PX / max(w, h)
    scale = min(scale_by_pixels, scale_by_side, 1.0)
    new_size = (max(1, int(w*scale)), max(1, int(h*scale)))
    return im.resize(new_size, Image.Resampling.LANCZOS)

def _dynamic_upscale_factor(im: Image.Image) -> int:
    """Choose 1x/2x/3x upsample based on current size to avoid OOM."""
    w, h = im.size
    mpx = (w * h) / 1e6
    if mpx <= 4:   # small images benefit from 3x
        return 3
    if mpx <= 9:   # medium → 2x
        return 2
    return 1       # large already

def _upsample(im: Image.Image, factor: int) -> Image.Image:
    if factor <= 1:
        return im
    w, h = im.size
    # also respect MAX_SIDE_PX
    target_w = min(int(w * factor), MAX_SIDE_PX)
    target_h = min(int(h * factor), MAX_SIDE_PX)
    return im.resize((target_w, target_h), Image.Resampling.LANCZOS)

def _edge_preserve_smooth(im: Image.Image) -> Image.Image:
    """Use bilateral only on moderate sizes; otherwise Gaussian fallback."""
    w, h = im.size
    if not HAS_CV2 or (w*h) > 9e6:  # >9MP → just Gaussian to save RAM
        return im.filter(ImageFilter.GaussianBlur(radius=max(1.2, GAUSS_AFTER_BILATERAL)))

    try:
        arr = np.array(im)
        arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        out_bgr = cv2.bilateralFilter(
            arr_bgr,
            d=BILATERAL_D,
            sigmaColor=BILATERAL_SIGMA_COLOR,
            sigmaSpace=BILATERAL_SIGMA_SPACE,
        )
        out_rgb = cv2.cvtColor(out_bgr, cv2.COLOR_BGR2RGB)
        out = Image.fromarray(out_rgb)
        if GAUSS_AFTER_BILATERAL > 0:
            out = out.filter(ImageFilter.GaussianBlur(radius=GAUSS_AFTER_BILATERAL))
        # free numpy arrays
        del arr, arr_bgr, out_bgr, out_rgb
        gc.collect()
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

def _get_darkest_palette_color(pal_img: Image.Image) -> Tuple[int,int,int]:
    if pal_img.mode != "P":
        pal_img = pal_img.quantize(colors=8, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    pal = pal_img.getpalette()
    used = {idx for _, idx in pal_img.getcolors(maxcolors=256) or []}
    darkest, min_y = (0,0,0), 1e9
    for idx in used:
        r,g,b = pal[idx*3: idx*3+3]
        y = 0.2126*r + 0.7152*g + 0.0722*b
        if y < min_y:
            min_y, darkest = y, (r,g,b)
    return darkest

def _rgb_to_hex(c: Tuple[int,int,int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*c)

def _make_mask_for_color(im_rgb: Image.Image, target: Tuple[int,int,int]) -> Image.Image:
    w, h = im_rgb.size
    mask = Image.new("1", (w, h), 0); mp = mask.load()
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
                                     auto_k_min: int = REINDEX_MIN_K,
                                     auto_k_max: int = REINDEX_MAX_K) -> bytes:
    # Load & normalize
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)

    # Keep size under control first
    im = _cap_size(im)

    # Adaptive upsample (small images get more love)
    up = _dynamic_upscale_factor(im)
    im = _upsample(im, up)

    # Dehalo & smoothing
    im = _dehalo_to_white(im, bg=None, dist_thresh=DEHALO_RGB_DIST, grow_px=DEHALO_GROW_PX)
    im = _edge_preserve_smooth(im)

    # Auto palette size
    approx_unique = len(im.convert("P", palette=Image.Palette.ADAPTIVE, colors=16).getcolors() or [])
    if approx_unique <= 3:
        k = 3
    elif approx_unique >= auto_k_max:
        k = auto_k_max
    else:
        k = max(auto_k_min, min(auto_k_max, approx_unique))

    # Regularize → reindex
    im_q = _quantize_no_dither(im, k); del im; gc.collect()
    im_smooth = _gentle_regularize(im_q); del im_q; gc.collect()
    im_final = _reindex_to_palette(im_smooth, k); del im_smooth; gc.collect()

    # ---- Pass A: Fills with VTracer
    png_path = _write_temp_image(im_final, ".png")
    fills_svg_fd, fills_svg_path = tempfile.mkstemp(suffix=".svg"); os.close(fills_svg_fd)
    rc, _, err = _run(["vtracer", "-i", png_path, "-o", fills_svg_path])
    if rc != 0:
        raise RuntimeError(f"vtracer failed: {err.decode('utf-8', 'ignore')}")

    # ---- Pass B: Strokes for darkest color with Potrace
    darkest = _get_darkest_palette_color(im_final)
    stroke_color_hex = _rgb_to_hex(darkest)
    mask = _make_mask_for_color(im_final, darkest)
    mask = mask.filter(ImageFilter.MinFilter(3))
    mask = mask.filter(ImageFilter.MinFilter(3))
    pbm_path = _write_temp_image(mask, ".pbm")
    del mask, im_final; gc.collect()

    stroke_svg_fd, stroke_svg_path = tempfile.mkstemp(suffix=".svg"); os.close(stroke_svg_fd)
    potrace_cmd = [
        "potrace", pbm_path, "--svg",
        "--turdsize", str(POTRACE_TURDSIZE),
        "--alphamax", str(POTRACE_ALPHAMAX),
        "--opttolerance", str(POTRACE_OPTTOL),
        "--turnpolicy", POTRACE_TURNPOL,
        "-o", stroke_svg_path,
    ]
    rc, _, err = _run(potrace_cmd)
    if rc != 0:
        raise RuntimeError(f"potrace failed: {err.decode('utf-8', 'ignore')}")

    # ---- Compose
    fills_tree = ET.parse(fills_svg_path); fills_root = fills_tree.getroot()
    stroke_tree = ET.parse(stroke_svg_path); stroke_root = stroke_tree.getroot()

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

    # Cleanup temps
    for p in (png_path, fills_svg_path, pbm_path, stroke_svg_path):
        try: os.remove(p)
        except OSError: pass
    gc.collect()

    return svg_bytes
