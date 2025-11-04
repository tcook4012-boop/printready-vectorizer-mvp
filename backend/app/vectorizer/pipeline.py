import cv2
import numpy as np
import base64
import subprocess
import tempfile
import uuid
import os

def vectorize_image(image_bytes):
    # Load image into OpenCV
    image_array = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if img is None:
        raise Exception("Failed to load image")

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Threshold using Otsu
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Save temp PNG
    tmp_input = f"/tmp/{uuid.uuid4()}.png"
    tmp_output = f"/tmp/{uuid.uuid4()}.svg"
    cv2.imwrite(tmp_input, thresh)

    # Run potrace
    cmd = ["potrace", "-s", tmp_input, "-o", tmp_output]
    subprocess.run(cmd, check=True)

    if not os.path.exists(tmp_output):
        raise Exception("Potrace failed")

    with open(tmp_output, "r", encoding="utf-8") as f:
        svg_data = f.read()

    # Cleanup
    os.remove(tmp_input)
    os.remove(tmp_output)

    return svg_data
