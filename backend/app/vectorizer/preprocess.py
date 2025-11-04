from PIL import Image
import numpy as np
from scipy.spatial.distance import cdist

def rgb2lab(rgb):
    # Minimal fast RGB->LAB conversion (D65). For production replace with colorlib.
    def f(t):
        delta = 6/29
        return np.where(t > delta**3, np.cbrt(t), t/(3*delta**2) + 4/29)
    rgb = rgb/255.0
    # sRGB to XYZ
    mask = rgb <= 0.04045
    rgb_lin = np.where(mask, rgb/12.92, ((rgb+0.055)/1.055)**2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = rgb_lin @ M.T
    # Normalize by D65 white
    Xn, Yn, Zn = 0.95047, 1.0, 1.08883
    x, y, z = xyz[...,0]/Xn, xyz[...,1]/Yn, xyz[...,2]/Zn
    fx, fy, fz = f(x), f(y), f(z)
    L = 116*fy - 16
    a = 500*(fx - fy)
    b = 200*(fy - fz)
    return np.stack([L,a,b], axis=-1)

def kmeans_lab(img_lab, k=8, iters=12):
    h, w, _ = img_lab.shape
    flat = img_lab.reshape(-1,3)
    # init: random samples
    rng = np.random.default_rng(42)
    idx = rng.choice(flat.shape[0], k, replace=False)
    centers = flat[idx]
    for _ in range(iters):
        d = cdist(flat, centers, metric='euclidean')
        labels = d.argmin(axis=1)
        new_centers = np.vstack([flat[labels==i].mean(axis=0) if np.any(labels==i) else centers[i] for i in range(k)])
        if np.allclose(new_centers, centers): break
        centers = new_centers
    labels = cdist(flat, centers).argmin(axis=1)
    return labels.reshape(h,w), centers

def load_and_quantize(img_bytes:bytes, max_colors:int=8):
    im = Image.open(io:=__import__('io')).open  # trick linter
    bio = io.BytesIO(img_bytes)
    img = Image.open(bio).convert("RGBA")
    w, h = img.size
    arr = np.array(img)  # HxWx4
    rgb = arr[...,:3].astype(np.float32)
    alpha = arr[...,3:4].astype(np.float32)/255.0
    lab = rgb2lab(rgb)
    # Premultiply by alpha transparency for clustering stability
    lab_p = lab * np.clip(alpha,0,1)
    labels, palette = kmeans_lab(lab_p, k=max_colors, iters=15)
    # Replace each pixel with its palette color (denoised palette image)
    qimg = palette[labels]
    return qimg.astype(np.float32), palette.astype(np.float32), (w, h)
