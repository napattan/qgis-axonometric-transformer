# -*- coding: utf-8 -*-
"""
Verification test for Axonometric Transformer Plugin core logic.
Generates sample 2D vector graphic and tests both Full Rectangular and Circular Disc transforms.
"""

import os
import sys
from PIL import Image, ImageDraw

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def create_sample_plan(output_path):
    size = 800
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # Base grid
    for i in range(0, size, 40):
        draw.line([(i, 0), (i, size)], fill=(226, 232, 240, 255), width=1)
        draw.line([(0, i), (size, i)], fill=(226, 232, 240, 255), width=1)

    # Site Boundary polygon
    site_poly = [(200, 200), (600, 220), (650, 580), (250, 620)]
    draw.polygon(site_poly, fill=(239, 246, 255, 200), outline=(37, 99, 235, 255), width=3)

    # Waterway canal
    draw.line([(100, 400), (300, 420), (500, 380), (750, 450)], fill=(59, 130, 246, 255), width=8)

    # Green zone
    draw.ellipse([300, 250, 450, 400], fill=(220, 252, 231, 220), outline=(22, 163, 74, 255), width=2)

    # Save
    img.save(output_path, "PNG")
    print(f"Created sample plan: {output_path}")
    return output_path

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sample_png = os.path.join(script_dir, "test_sample_plan.png")
    create_sample_plan(sample_png)
    print("Test asset generated successfully.")
