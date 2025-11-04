import numpy as np

def sobel_edges(gray):
    # Simple Sobel magnitude
    Kx = np.array([[1,0,-1],[2,0,-2],[1,0,-1]], dtype=np.float32)
    Ky = np.array([[1,2,1],[0,0,0],[-1,-2,-1]], dtype=np.float32)
    gx = conv2(gray, Kx)
    gy = conv2(gray, Ky)
    mag = np.hypot(gx, gy)
    mag /= (mag.max()+1e-6)
    return mag

def conv2(img, kernel):
    kh, kw = kernel.shape
    pad_h, pad_w = kh//2, kw//2
    padded = np.pad(img, ((pad_h,pad_h),(pad_w,pad_w)), mode='edge')
    out = np.zeros_like(img, dtype=np.float32)
    for y in range(img.shape[0]):
        for x in range(img.shape[1]):
            patch = padded[y:y+kh, x:x+kw]
            out[y,x] = (patch*kernel).sum()
    return out

def extract_contours(img_lab, min_feature_px=4):
    # Treat each unique Lab color region as a mask, get its edges/contours.
    # For MVP, collapse Lab to a single channel (L) to find edges.
    L = img_lab[...,0]
    edges = sobel_edges(L)
    # Threshold edges
    thr = 0.2
    binary = (edges>thr).astype(np.uint8)
    # Trace closed contours via Moore-Neighbor
    visited = np.zeros_like(binary, dtype=bool)
    H, W = binary.shape
    paths = []  # list of dicts: {"points":[(x,y),...], "color":(L,a,b)}
    def neighbors(y,x):
        return [(y-1,x-1),(y-1,x),(y-1,x+1),(y,x+1),(y+1,x+1),(y+1,x),(y+1,x-1),(y,x-1)]
    for y in range(H):
        for x in range(W):
            if binary[y,x] and not visited[y,x]:
                # contour trace
                cy,cx = y,x
                contour = []
                prev_dir = 7  # coming from left
                while True:
                    visited[cy,cx]=True
                    contour.append((cx,cy))
                    # search starting from prev_dir+1
                    found=False
                    for i in range(8):
                        di = (prev_dir + 1 + i) % 8
                        ny,nx = neighbors(cy,cx)[di]
                        if 0<=ny<H and 0<=nx<W and binary[ny,nx] and not visited[ny,nx]:
                            cy,cx = ny,nx
                            prev_dir = di
                            found=True
                            break
                    if not found:
                        break
                if len(contour)>=min_feature_px:
                    paths.append({"points":contour, "color":(1,0,0)})
    return paths
