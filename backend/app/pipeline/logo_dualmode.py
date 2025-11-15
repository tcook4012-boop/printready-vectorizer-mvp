# backend/app/pipeline/logo_dualmode.py

"""
Dual-mode router for logo vs sign/text artwork.

- 'logo' mode  -> mascot / complex logo pipeline (logo_logo_mode)
- 'sign' mode  -> sign/text pipeline (logo_sign_mode)

The caller (FastAPI endpoint) only needs to call:
    vectorize_logo_dualmode_to_svg_bytes(image_bytes)
"""

import io

from PIL import Image

from .logo_logo_mode import vectorize_logo_logo_mode_to_svg_bytes
from .logo_sign_mode import vectorize_logo_sign_mode_to_svg_bytes
# You can keep logo_safe around as a backup if you like:
# from .logo_safe import vectorize_logo_safe_to_svg_bytes


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
    - Otherwise -> 'sign' (flat 1–4 color sign / text / low-color logo).
    """
    approx_unique = _estimate_unique_colors(im)

    if approx_unique >= 5:
        return "logo"
    return "sign"


# ---------- public entrypoint ----------


def vectorize_logo_dualmode_to_svg_bytes(image_bytes: bytes) -> bytes:
    """
    Router that decides which pipeline to use based on the input artwork.

    - 'sign'  -> sign/text pipeline (logo_sign_mode)
    - 'logo'  -> mascot/complex logo pipeline (logo_logo_mode)
    """
    # Decode once here for routing
    im = Image.open(io.BytesIO(image_bytes))
    im = _to_srgb_rgba(im)
    im = _composite_over_white(im)

    mode = _decide_mode(im)

    if mode == "logo":
        # ELON-style artwork, or any multi-color mascot-type logo
        return vectorize_logo_logo_mode_to_svg_bytes(image_bytes)

    # default / fallback: sign/text / low-color logo mode
    return vectorize_logo_sign_mode_to_svg_bytes(image_bytes)
