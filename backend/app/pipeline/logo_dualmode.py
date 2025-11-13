# backend/app/pipeline/logo_dualmode.py

"""
Thin wrapper around the current logo_safe pipeline.

Right now this just delegates to the baseline logo_safe implementation, so
behaviour is IDENTICAL to your existing system.

The point of this file is to give us a stable place to implement smarter
"logo vs sign" routing and future improvements without touching the FastAPI
endpoint or your original baseline snapshot.
"""

from typing import Literal

from .logo_safe import vectorize_logo_safe_to_svg_bytes as _baseline_vectorize

# In the future we'll support:
#   - "auto"      → analyze image and pick best mode
#   - "logo"      → flatter, more aggressive smoothing (ELON-style art)
#   - "sign"      → text-safe, detail-preserving (Murillo, PECANS, flags)
Mode = Literal["auto", "logo", "sign"]


def _analyze_mode(image_bytes: bytes) -> Mode:
    """
    Placeholder for future image analysis.

    For now we always return "auto" and simply delegate to the baseline
    pipeline. When we implement true dual-mode behaviour, this function will
    inspect the image (density of thin strokes, number of colors, etc) and
    choose "logo" vs "sign".
    """
    return "auto"


def vectorize_logo_dualmode_to_svg_bytes(
    image_bytes: bytes,
    mode: Mode = "auto",
) -> bytes:
    """
    Entry point used by FastAPI.

    CURRENT BEHAVIOUR:
    -------------------
    We always call the existing logo_safe pipeline, so the output is
    identical to your current system.

    FUTURE BEHAVIOUR:
    ------------------
    - If mode == "logo":   use logo-optimised settings
    - If mode == "sign":   use sign/text-optimised settings
    - If mode == "auto":   call _analyze_mode(...) to decide

    Keeping the API signature stable means the FastAPI endpoint doesn't need
    to change when we improve the internals.
    """
    # For now we ignore the mode and call the baseline pipeline directly.
    # This guarantees no behavioural change while we wire up the architecture.
    _ = _analyze_mode(image_bytes)  # noqa: F841 (unused for now)
    return _baseline_vectorize(image_bytes)
