# backend/app/pipeline/logo_dualmode.py

import io

from PIL import Image

from .logo_logo_mode import vectorize_logo_logo_mode_to_svg_bytes
from .logo_sign_mode import vectorize_logo_sign_mode_to_svg_bytes


# ---------- small helpers (minimal copy of logo_safe helpers) ----------


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


def _estimate_unique_colors(im: Image.Image) -> int:
    """
    Rough estimate of how many 'meaningful' colors the artwork has.

    We quantize to 16 colors on a downscaled version and count how many
    palette entries are actually used.
    """
    thumb = im.copy()
    thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)
    pal = thumb.convert("P", palette=Image.Palette.ADAPTIVE, colors=16)
    colors = pal.getcolors(maxcolors=256) or []
    return len(colors)


def _decide_mode(im: Image.Image) -> str:
    """
    Heuristic router:

    - If we see 5 or more distinct colors -> 'logo' (mascot / complex logo).
    - Otherwise -> 'sign' (flat 1–4 color sign / text).
    """
    approx_unique = _estimate_unique_colors(im)

    if approx_unique >= 5:
        return "logo"
    return "sign"


def vectorize_logo_dualmode_to_svg_bytes(image_bytes: bytes) -> bytes:
    """
    Route to either the sign pipeline or the mascot/logo pipeline
    based on the number of distinct colors.
    """
    # Decode once here for routing
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)

    mode = _decide_mode(im)

    if mode == "logo":
        # ELON-style mascot artwork comes here
        return vectorize_logo_logo_mode_to_svg_bytes(image_bytes)

    # default / fallback: sign/text mode
    return vectorize_logo_sign_mode_to_svg_bytes(image_bytes)
