# backend/app/pipeline/logo_dualmode.py

"""
Dual-mode wrapper around the existing logo_safe pipeline.

GOAL
----
Provide two separate "flavours" of vectorization:

  - "sign"  → text-safe, detail-preserving (yard signs, PECANS, Murillo)
  - "logo"  → logo/mascot friendly (ELON, patches), where we can safely make
              different post-processing choices (e.g. remove extra outlines).

Right now the "sign" path is exactly your baseline pipeline.
The "logo" path also uses the baseline pipeline but then strips the Potrace
stroke overlay group ("stroke-layer") that was causing the faint red outline.

We also have a very light "auto" mode that uses a quick color-count heuristic
to choose between "sign" and "logo".
"""

from typing import Literal
import io
import xml.etree.ElementTree as ET

from PIL import Image

# This is the current production pipeline implementation.
from .logo_safe import vectorize_logo_safe_to_svg_bytes as _baseline_vectorize

# Public mode type. FastAPI currently always calls this with the default "auto".
Mode = Literal["auto", "logo", "sign"]


def _approx_unique_colors(image_bytes: bytes, max_colors: int = 16) -> int:
    """
    Approximate the number of distinct colors in the input image.

    We intentionally keep this very cheap: quantize down to a small adaptive
    palette and count how many entries are actually used.
    """
    im = Image.open(io.BytesIO(image_bytes))
    # Normalize to RGB to keep things simple
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    if im.mode == "RGBA":
        # Flatten over white so transparent backgrounds don't explode the palette
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im).convert("RGB")

    pal_img = im.convert("P", palette=Image.Palette.ADAPTIVE, colors=max_colors)
    colors = pal_img.getcolors(maxcolors=max_colors)
    if not colors:
        return 0
    return len(colors)


def _analyze_mode(image_bytes: bytes) -> Mode:
    """
    Very simple heuristic for now:

      - If the image has 4 or more distinct colors → treat as "logo"
        (e.g. ELON: white, yellow/gold, maroon, black)
      - Otherwise → treat as "sign" (typical 2–3 color yard signs)

    This keeps PECANS / Murillo in the conservative "sign" path while pushing
    ELON-style art into the "logo" path where we can safely tweak behaviour.
    """
    try:
        n = _approx_unique_colors(image_bytes)
    except Exception:
        # If anything goes wrong, fall back to the safest option.
        return "sign"

    if n >= 4:
        return "logo"
    return "sign"


def _vectorize_sign_like(image_bytes: bytes) -> bytes:
    """
    Sign/text-safe variant.

    CURRENTLY:
      - This is EXACTLY your baseline pipeline. No extra processing.

    This is what we want for PECANS, Murillo, and similar sign artwork where
    text sharpness and strict color separation are critical.
    """
    return _baseline_vectorize(image_bytes)


def _remove_stroke_layer(svg_bytes: bytes) -> bytes:
    """
    Remove the Potrace stroke overlay group ("stroke-layer") from the SVG.

    In the baseline pipeline, we:
      - Vectorize fills with VTracer
      - Extract the darkest color and trace it with Potrace
      - Overlay a <g id="stroke-layer"> with stroke-only paths

    For ELON-style logos this can create a faint outline around everything.
    Stripping just that group keeps the fills and overall shapes from the
    baseline while eliminating the extra outline.

    If anything goes wrong while parsing, we just return the original bytes.
    """
    try:
        root = ET.fromstring(svg_bytes)

        # Namespaces may or may not be present; handle both cases.
        def _tag_name(tag: str) -> str:
            return tag.split("}", 1)[-1] if "}" in tag else tag

        # Walk the tree and find any group with id="stroke-layer"
        to_remove = []
        for parent in root.iter():
            for child in list(parent):
                if _tag_name(child.tag) == "g" and child.attrib.get("id") == "stroke-layer":
                    to_remove.append((parent, child))

        if not to_remove:
            # Nothing to strip; return as-is.
            return svg_bytes

        for parent, child in to_remove:
            parent.remove(child)

        # Serialize back to bytes
        return ET.tostring(root, encoding="utf-8", method="xml")
    except Exception:
        # On any failure, keep the original SVG.
        return svg_bytes


def _vectorize_logo_like(image_bytes: bytes) -> bytes:
    """
    Logo/mascot variant.

    CURRENTLY:
      - Run the same baseline pipeline as "sign" mode
      - Then strip the Potrace stroke overlay group to remove the extra outline

    This should:
      - Keep the ELON colors and shapes
      - Remove the faint red edge around everything
      - Avoid changing behaviour for signs (they stay on the sign path)
    """
    base_svg = _baseline_vectorize(image_bytes)
    cleaned_svg = _remove_stroke_layer(base_svg)
    return cleaned_svg


def vectorize_logo_dualmode_to_svg_bytes(
    image_bytes: bytes,
    mode: Mode = "auto",
) -> bytes:
    """
    Single entry point used by FastAPI.

    - mode="auto": backend chooses between "sign" and "logo"
    - mode="sign": force sign/text-optimised path
    - mode="logo": force logo/mascot-optimised path
    """
    # Resolve "auto" into a concrete mode.
    if mode == "auto":
        inferred = _analyze_mode(image_bytes)
        if inferred in ("logo", "sign"):
            mode = inferred
        else:
            mode = "sign"

    if mode == "logo":
        return _vectorize_logo_like(image_bytes)
    else:
        # Default to the sign-safe path
        return _vectorize_sign_like(image_bytes)
