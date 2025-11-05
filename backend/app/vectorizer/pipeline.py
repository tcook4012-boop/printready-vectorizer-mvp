import subprocess
import tempfile
import os
from PIL import Image
from typing import Optional


def _png_to_pnm(png_bytes: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_png:
        tmp_png.write(png_bytes)
        tmp_png.flush()
        png_path = tmp_png.name

    pnm_path = png_path.replace(".png", ".pnm")

    try:
        img = Image.open(png_path)
        img = img.convert("L")  # grayscale (potrace needs 1-channel)
        img.save(pnm_path, format="PPM")
    except Exception as e:
        raise RuntimeError(f"PNM conversion failed: {e}")

    with open(pnm_path, "rb") as f:
        pnm_bytes = f.read()

    # cleanup png and pnm
    os.remove(png_path)
    os.remove(pnm_path)

    return pnm_bytes


def _run_potrace(png_bytes: bytes) -> str:
    # ✅ Convert PNG → PNM first
    pnm_bytes = _png_to_pnm(png_bytes)

    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "in.pnm")
        out_path = os.path.join(tmpdir, "out.svg")

        with open(in_path, "wb") as f:
            f.write(pnm_bytes)

        cmd = [
            "potrace",
            in_path,
            "-s",
            "-o",
            out_path
        ]

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise RuntimeError(f"potrace error: {proc.stderr.decode()}")

        with open(out_path, "r") as f:
            svg_text = f.read()

        return svg_text


def vectorize_image(
    image_bytes: bytes,
    max_colors: int = 8,
    smoothness: str = "medium",
    primitive_snap: bool = True
) -> str:
    try:
        return _run_potrace(image_bytes)
    except Exception as e:
        return f"Vectorization failed: {e}"
