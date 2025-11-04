import os
import tempfile
import subprocess
from fastapi import HTTPException
from PIL import Image

def _png_to_pbm(src_img_path: str) -> str:
    """Convert any raster (e.g., PNG/JPG) to 1-bit PBM for potrace."""
    try:
        img = Image.open(src_img_path).convert("L")       # grayscale
        # Simple binarize. Tweak threshold if you like.
        img = img.point(lambda p: 255 if p > 200 else 0)
        img = img.convert("1")                            # 1-bit image
        fd, pbm_path = tempfile.mkstemp(suffix=".pbm")
        os.close(fd)
        img.save(pbm_path)                                # PBM inferred from extension
        return pbm_path
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Raster-to-PBM conversion failed: {e}")

def vectorize_image(raster_path: str) -> str:
    """Run potrace on the given raster image and return path to SVG."""
    pbm_path = _png_to_pbm(raster_path)

    fd, svg_path = tempfile.mkstemp(suffix=".svg")
    os.close(fd)

    cmd = ["potrace", pbm_path, "-s", "-o", svg_path]     # “-s” == SVG output
    # Optional tuning flags you can add later:
    # cmd += ["--turdsize", "10", "--alphamax", "1.0", "--opttolerance", "0.2"]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"potrace failed (exit {proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
            )
        return svg_path
    finally:
        # Keep SVG; clean PBM
        try:
            os.remove(pbm_path)
        except Exception:
            pass
