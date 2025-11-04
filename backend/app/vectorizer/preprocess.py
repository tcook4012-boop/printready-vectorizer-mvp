import io
from PIL import Image
import numpy as np
from scipy.spatial.distance import cdist

# --------------------------------------------
# Utility functions
# --------------------------------------------

def rgb2lab(rgb):
    """Convert an RGB image (0-255) to CIELAB space."""
    rgb = np.clip(rgb / 255.0, 0, 1)
    mask = rgb <= 0.04045
    rgb[mask] = rgb[mask] / 12.92
    rgb[~mask] = ((rgb[~mask] + 0.055) / 1.055) ** 2.4

    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    X = r * 0.4124 + g * 0.3576 + b * 0.1805
    Y = r * 0.2126 + g * 0.7152 + b * 0.0722
    Z = r * 0.0193 + g * 0.1192 + b * 0.9505

    X /= 0.95047
    Z /= 1.08883
    XYZ = np.stack([X, Y, Z], axis=-1)
    mask = XYZ > 0.008856
    XYZ[mask] = np.cbrt(XYZ[mask])
    XYZ[~mask] = (7.787 * XYZ[~mask]) + (16.0 / 116.0)

    L = (116.0 * XYZ[..., 1]) - 16.0
    a = 500.0 * (XYZ[..., 0] - XYZ[..., 1])
    b = 200.0 * (XYZ[..., 1] - XYZ[..., 2])
    return np.stack([L, a, b], axis=-1)


def lab2rgb(lab):
    """Convert LAB back to RGB (0-255)."""
    Y = (lab[..., 0] + 16.0) / 116.0
    X = lab[..., 1] / 500.0 + Y
    Z = Y - lab[..., 2] / 200.0
    X = np.clip(X, 0, None)
    Y = np.clip(Y, 0, None)
    Z = np.clip(Z, 0, None)

    XYZ = np.stack([X, Y, Z], axis=-1)
    XYZ[..., 0] *= 0.95047
    XYZ[..., 2] *= 1.08883

    rgb = np.zeros_like(XYZ)
    rgb[..., 0] = XYZ[..., 0] * 3.2406 + XYZ[..., 1] * (-1.5372) + XYZ[..., 2] * (-0.4986)
    rgb[..., 1] = XYZ[..., 0] * (-0.9689) + XYZ[..., 1] * 1.8758 + XYZ[..., 2] * 0.0415
    rgb[..., 2] = XYZ[..., 0] * 0.0557 + XYZ[..., 1] * (-0.2040) + XYZ[..., 2] * 1.0570

    mask = rgb > 0.0031308
    rgb[mask] = 1.055 * (rgb[mask] ** (1 / 2.4)) - 0.055
    rgb[~mask] = rgb[~mask] * 12.92

    rgb = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
    return rgb


def kmeans_lab(pixels, k=8, iters=15):
    """Simple K-means clustering in LAB space."""
    pixels = pixels.reshape(-1, 3)
    idx = np.random.choice(len(pixels), k, replace=False)
    centers = pixels[idx]

    for _ in range(iters):
        dists = cdist(pixels, centers)
        labels = np.argmin(dists, axis=1)
        new_centers = np.array([pixels[labels == i].mean(axis=0) if np.any(labels == i) else centers[i] for i in range(k)])
        if np.allclose(centers, new_centers, atol=1e-3):
            break
        centers = new_centers

    return labels.reshape(-1, 1), centers


# --------------------------------------------
# Main preprocessing function
# --------------------------------------------

def load_and_quantize(img_bytes: bytes, max_colors: int = 8):
    """Load image bytes, quantize to limited palette in LAB color space."""
    bio = io.BytesIO(img_bytes)
    img = Image.open(bio).convert("RGBA")
    w, h = img.size
    arr = np.array(img)  # HxWx4
    rgb = arr[..., :3].astype(np.float32)
    alpha = arr[..., 3:4].astype(np.float32) / 255.0
    lab = rgb2lab(rgb)
    lab_p = lab * np.clip(alpha, 0, 1)
    labels, palette = kmeans_lab(lab_p, k=max_colors, iters=15)
    qimg = palette[labels.flatten()].reshape(h, w, 3)
    return qimg.astype(np.float32), palette.astype(np.float32), (w, h)
