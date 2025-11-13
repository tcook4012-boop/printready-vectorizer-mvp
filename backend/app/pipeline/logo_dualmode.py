# backend/app/pipeline/logo_dualmode.py

"""
Dual-mode wrapper around the existing logo_safe pipeline.

GOAL
----
Provide two separate "flavours" of vectorization:

  - "sign"  → text-safe, detail-preserving (yard signs, PECANS, Murillo)
  - "logo"  → logo/mascot friendly, can smooth curves a bit more (ELON, patches)

Right now BOTH modes still call the same baseline pipeline so behaviour is
identical to your current system. This file just creates a clean place to
evolve the internals without touching FastAPI or the baseline snapshot.

We also keep a tiny "auto" mode hook so later we can have the backend choose
between "sign" and "logo" automatically.
"""

from typing import Literal

# This is the current production pipeline implementation.
from .logo_safe import vectorize_logo_safe_to_svg_bytes as _baseline_vectorize

# Public mode type. FastAPI currently always calls this with the default "auto".
Mode = Literal["auto", "logo", "sign"]


def _analyze_mode(image_bytes: bytes) -> Mode:
    """
    Placeholder for future image analysis.

    Eventually this will inspect the image (colors, stroke thickness, text
    density, etc.) and return "logo" or "sign".

    For now we simply return "sign" as a conservative default. Since both
    paths currently call the same baseline pipeline, this does not change
    behaviour at all.
    """
    return "sign"


def _vectorize_sign_like(image_bytes: bytes) -> bytes:
    """
    Sign/text-safe variant.

    CURRENTLY:
      - Just calls the baseline pipeline.

    FUTURE:
      - Keep edges crisp
      - Avoid shrinking text
      - Aggressively kill halos without over-blurring
    """
    return _baseline_vectorize(image_bytes)


def _vectorize_logo_like(image_bytes: bytes) -> bytes:
    """
    Logo/mascot variant.

    CURRENTLY:
      - Just calls the baseline pipeline.

    FUTURE:
      - Slightly more smoothing for curves
      - More tolerant of organic shapes
      - Extra care around color separation (no unwanted outlines)
    """
    return _baseline_vectorize(image_bytes)


def vectorize_logo_dualmode_to_svg_bytes(
    image_bytes: bytes,
    mode: Mode = "auto",
) -> bytes:
    """
    Single entry point used by FastAPI.

    - mode="auto": backend chooses between "sign" and "logo" (later)
    - mode="sign": force sign/text-optimised path
    - mode="logo": force logo/mascot-optimised path

    At the moment both paths are identical and use the baseline pipeline, so
    this wrapper is behaviourally neutral.
    """
    # Resolve "auto" into a concrete mode.
    if mode == "auto":
        inferred = _analyze_mode(image_bytes)
        if inferred in ("logo", "sign"):
            mode = inferred
        else:
            # Safety fallback – never return "auto" from the analyser.
            mode = "sign"

    if mode == "logo":
        return _vectorize_logo_like(image_bytes)
    else:
        # Default to the sign-safe path for now.
        return _vectorize_sign_like(image_bytes)
