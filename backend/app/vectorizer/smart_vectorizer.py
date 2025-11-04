# backend/app/vectorizer/smart_vectorizer.py

import io
import cv2
import numpy as np
from PIL import Image
from realesrgan import RealESRGANer
from basicsr.archs.rrdbnet_arch import RRDBNet
import subprocess
import tempfile
import os
from pathlib import Path

class SmartVectorizer:
    """
    High-quality vectorizer using:
    1. Real-ESRGAN upscaling (removes JPG artifacts)
    2. Perceptual color quantization (LAB space)
    3. Potrace for actual tracing (but with clean input)
    """
    
    def __init__(self):
        # Initialize Real-ESRGAN model (runs once at startup)
        self.upsampler = None
        self._init_upsampler()
    
    def _init_upsampler(self):
        """Load the AI upscaling model"""
        try:
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, 
                          num_block=23, num_grow_ch=32, scale=2)
            
            model_path = 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth'
            
            self.upsampler = RealESRGANer(
                scale=2,
                model_path=model_path,
                model=model,
                tile=400,
                tile_pad=10,
                pre_pad=0,
                half=False  # Use FP32 for CPU compatibility
            )
        except Exception as e:
            print(f"Warning: Could not load Real-ESRGAN: {e}")
            self.upsampler = None
    
    def vectorize(self, image_bytes: bytes, max_colors: int = 8, smoothness: str = "medium"):
        """
        Main vectorization pipeline
        Returns: (svg_bytes, metrics_dict)
        """
        
        # 1. Load image
        img = self._load_image(image_bytes)
        original_size = img.shape[:2]
        
        # 2. AI upscale (if available) - this is the game changer
        if self.upsampler is not None and min(img.shape[:2]) < 800:
            try:
                img, _ = self.upsampler.enhance(img, outscale=2)
            except Exception as e:
                print(f"Upscaling failed, using original: {e}")
        
        # 3. Denoise (removes compression artifacts)
        img = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
        
        # 4. Quantize colors in LAB space (perceptually uniform)
        img_quantized = self._quantize_colors_lab(img, max_colors)
        
        # 5. Separate into color layers and trace each
        svg_content = self._trace_color_layers(img_quantized, smoothness)
        
        # 6. Build final SVG
        svg_bytes = self._build_svg(svg_content, original_size)
        
        metrics = {
            "width": original_size[1],
            "height": original_size[0],
            "colors": max_colors,
            "layers": len(svg_content)
        }
        
        return svg_bytes, metrics
    
    def _load_image(self, image_bytes: bytes):
        """Load image from bytes"""
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    
    def _quantize_colors_lab(self, img, n_colors):
        """Reduce colors using LAB color space (perceptually uniform)"""
        
        # Convert to LAB
        img_lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        
        # Reshape to pixel list
        pixels = img_lab.reshape(-1, 3).astype(np.float32)
        
        # K-means clustering
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
        _, labels, palette = cv2.kmeans(
            pixels, n_colors, None, criteria, 10, cv2.KMEANS_PP_CENTERS
        )
        
        # Reconstruct quantized image
        quantized_lab = palette[labels.flatten()].reshape(img_lab.shape)
        quantized_bgr = cv2.cvtColor(quantized_lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
        
        return quantized_bgr
    
    def _trace_color_layers(self, img, smoothness):
        """Trace each color as a separate layer using Potrace"""
        
        # Extract unique colors
        colors = self._get_unique_colors(img)
        
        svg_layers = []
        
        # Map smoothness to Potrace parameters
        smooth_params = {
            "low": {"alphamax": 0.0, "opttolerance": 0.1},
            "medium": {"alphamax": 1.0, "opttolerance": 0.2},
            "high": {"alphamax": 1.5, "opttolerance": 0.4}
        }
        params = smooth_params.get(smoothness, smooth_params["medium"])
        
        for color_bgr in colors:
            # Create binary mask for this color
            mask = self._create_color_mask(img, color_bgr)
            
            # Skip if mask is too small
            if cv2.countNonZero(mask) < 10:
                continue
            
            # Trace this mask with Potrace
            svg_path = self._trace_mask_with_potrace(mask, params)
            
            if svg_path:
                # Convert BGR to RGB hex
                color_hex = self._bgr_to_hex(color_bgr)
                svg_layers.append({
                    "path": svg_path,
                    "fill": color_hex
                })
        
        return svg_layers
    
    def _get_unique_colors(self, img):
        """Get list of unique colors in image"""
        pixels = img.reshape(-1, 3)
        unique_colors = np.unique(pixels, axis=0)
        return unique_colors
    
    def _create_color_mask(self, img, target_color):
        """Create binary mask for a specific color"""
        lower = np.array(target_color) - 1
        upper = np.array(target_color) + 1
        mask = cv2.inRange(img, lower, upper)
        return mask
    
    def _trace_mask_with_potrace(self, mask, params):
        """Use Potrace to trace a binary mask"""
        
        try:
            # Create temp files
            with tempfile.NamedTemporaryFile(suffix='.bmp', delete=False) as tmp_bmp:
                bmp_path = tmp_bmp.name
                cv2.imwrite(bmp_path, mask)
            
            with tempfile.NamedTemporaryFile(suffix='.svg', delete=False) as tmp_svg:
                svg_path = tmp_svg.name
            
            # Run Potrace
            cmd = [
                'potrace',
                bmp_path,
                '-s',  # SVG output
                '-o', svg_path,
                '--turdsize', '2',  # Remove 2px specks
                '--alphamax', str(params['alphamax']),
                '--opttolerance', str(params['opttolerance'])
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Read SVG path data
            if os.path.exists(svg_path):
                with open(svg_path, 'r') as f:
                    svg_content = f.read()
                    # Extract just the path data
                    import re
                    path_match = re.search(r'd="([^"]+)"', svg_content)
                    if path_match:
                        return path_match.group(1)
            
            # Cleanup
            os.unlink(bmp_path)
            if os.path.exists(svg_path):
                os.unlink(svg_path)
            
        except Exception as e:
            print(f"Potrace failed: {e}")
            return None
        
        return None
    
    def _bgr_to_hex(self, bgr):
        """Convert BGR tuple to hex color"""
        b, g, r = [int(x) for x in bgr]
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def _build_svg(self, svg_layers, original_size):
        """Combine all layers into final SVG"""
        
        height, width = original_size
        
        svg_parts = [
            f'<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        ]
        
        for layer in svg_layers:
            svg_parts.append(
                f'<path d="{layer["path"]}" fill="{layer["fill"]}" stroke="none" fill-rule="evenodd"/>'
            )
        
        svg_parts.append('</svg>')
        
        return '\n'.join(svg_parts).encode('utf-8')
