# backend/app/pipeline/logo_dualmode.py

"""
Dual-mode wrapper around the existing pipelines.

  - "sign"  → uses logo_safe (your current sign / text pipeline)
  - "logo"  → uses logo_logo_mode (new ELON-friendly pipeline)

Signs (PECANS, Murillo) should classify as "sign".
ELON-style mascots should classify as "logo".
"""

from typing import Literal
import io

from PIL import Image

# Pipelines
from .logo_safe import vectorize_logo_safe_to_svg_bytes as _sign_vectorize
from .logo_logo_mode import vectorize_logo_logo_mode_to_svg_bytes as _logo_vectorize

Mode = Literal["auto", "logo", "sign"]


# =========================
# Simple mode analysis
# =========================

def _approx_unique_colors(image_bytes: bytes, max_colors: int = 8) -> int:
    """
    Approximate number of distinct colors in the input.

    We keep this very cheap and robust. It is only used for a coarse decision
    between "sign" and "logo".
    """
    im = Image.open(io.BytesIO(image_bytes))

    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    if im.mode == "RGBA":
        from PIL import Image as PILImage  # avoid confusion with imported Image
        bg = PILImage.new("RGBA", im.size, (255, 255, 255, 255))
        im = PILImage.alpha_composite(bg, im).convert("RGB")

    pal_img = im.convert("P", palette=Image.Palette.ADAPTIVE, colors=max_colors)
    colors = pal_img.getcolors(maxcolors=max_colors)
    if not colors:
        return 0
    return len(colors)


def _analyze_mode(image_bytes: bytes) -> Mode:
    """
    Heuristic:

      - <= 3 colors → likely a simple sign (PECANS, many yard signs) → "sign"
      - >= 4 colors → more logo-like (ELON: white, gold, maroon, black) → "logo"

    This is intentionally simple and easy to tweak later if we see mis-classified
    examples in your real workload.
    """
    try:
        n = _approx_unique_colors(image_bytes)
    except Exception:
        return "sign"

    if n >= 4:
        return "logo"
    return "sign"


# =========================
# Public entry point
# =========================

def vectorize_logo_dualmode_to_svg_bytes(
    image_bytes: bytes,
    mode: Mode = "auto",
) -> bytes:
    """
    Entry point used by FastAPI.

      - mode="auto": infer "sign" vs "logo" from the image
      - mode="sign": force the sign pipeline
      - mode="logo": force the logo pipeline
    """
    if mode == "auto":
        inferred = _analyze_mode(image_bytes)
        if inferred in ("logo", "sign"):
            mode = inferred
        else:
            mode = "sign"

    if mode == "logo":
        return _logo_vectorize(image_bytes)
    else:
        return _sign_vectorize(image_bytes)
