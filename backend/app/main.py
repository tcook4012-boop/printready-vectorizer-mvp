import io
import numpy as np
import cv2
from flask import Flask, request, jsonify
from flask_cors import CORS
import potrace
from PIL import Image

app = Flask(__name__)
CORS(app)

@app.route("/vectorize", methods=["POST"])
def vectorize():
    try:
        file = request.files["file"]
        img_bytes = file.read()

        # Load with Pillow
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img = np.array(pil_img)

        # ---- STEP 1: Convert to grayscale ----
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # ---- STEP 2: Adaptive threshold (keeps letters hollow & crisp) ----
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31, 8
        )

        # ---- STEP 3: Remove tiny specks (opens small noise) ----
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        # ---- STEP 4: Convert to bitmap for Potrace ----
        bitmap = potrace.Bitmap(binary)
        path = bitmap.trace()

        # ---- STEP 5: Build SVG output ----
        svg_paths = []
        for curve in path:
            svg = '<path d="'
            start = curve.start_point
            svg += f"M{start.x} {start.y}"

            for seg in curve.segments:
                if seg.is_corner:
                    svg += f" L{seg.c.x} {seg.c.y}"
                    svg += f" L{seg.end_point.x} {seg.end_point.y}"
                else:
                    svg += (
                        f" C{seg.c1.x} {seg.c1.y},"
                        f"{seg.c2.x} {seg.c2.y},"
                        f"{seg.end_point.x} {seg.end_point.y}"
                    )

            svg += '" fill="black" stroke="none"/>'
            svg_paths.append(svg)

        svg_output = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{img.shape[1]}" height="{img.shape[0]}" '
            'viewBox="0 0 {w} {h}">'.format(w=img.shape[1], h=img.shape[0])
            + "".join(svg_paths)
            + "</svg>"
        )

        return jsonify({"svg": svg_output})

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "running"})
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
