# -*- coding: utf-8 -*-
"""Generate clean SVG and PNG icons for the QGIS Axonometric Transformer Plugin."""
import os
from PIL import Image, ImageDraw

def generate_icons(output_dir):
    size = 128
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw 3D Axonometric Map Plate
    cx, cy = size / 2, size / 2
    r = 44
    ratio = 0.57735  # Isometric
    ry = r * ratio
    depth = 16

    # Bottom slab
    slab_pts = [
        (cx - r, cy),
        (cx - r, cy + depth),
        (cx, cy + ry + depth),
        (cx + r, cy + depth),
        (cx + r, cy),
        (cx, cy + ry)
    ]
    # Draw cylinder base
    # Bottom ellipse arc
    draw.polygon(slab_pts, fill=(148, 163, 184, 255), outline=(100, 116, 139, 255))

    # Top floating isometric plate
    draw.ellipse([cx - r, cy - ry, cx + r, cy + ry], fill=(37, 99, 235, 240), outline=(29, 78, 216, 255), width=3)

    # Inner map contour lines (isometric curves)
    # Stream / Khlong curve
    draw.arc([cx - r*0.7, cy - ry*0.7, cx + r*0.7, cy + ry*0.7], 30, 210, fill=(147, 197, 253, 255), width=3)
    
    # Tiny site point
    draw.ellipse([cx - 4, cy - 3, cx + 4, cy + 3], fill=(255, 255, 255, 255), outline=(29, 78, 216, 255), width=2)

    # Save PNG
    png_path = os.path.join(output_dir, "icon.png")
    img.save(png_path, "PNG")
    print(f"Generated {png_path}")

    # Generate clean SVG
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <defs>
    <linearGradient id="plateGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#3b82f6"/>
      <stop offset="100%" stop-color="#1d4ed8"/>
    </linearGradient>
    <linearGradient id="baseGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#cbd5e1"/>
      <stop offset="100%" stop-color="#94a3b8"/>
    </linearGradient>
  </defs>
  <!-- Base Pedestal -->
  <path d="M 20 64 L 20 80 A 44 25.4 0 0 0 108 80 L 108 64 A 44 25.4 0 0 1 20 64 Z" fill="url(#baseGrad)" stroke="#64748b" stroke-width="2"/>
  <ellipse cx="64" cy="80" rx="44" ry="25.4" fill="none" stroke="#64748b" stroke-width="2"/>
  
  <!-- Top Axonometric Plate -->
  <ellipse cx="64" cy="64" rx="44" ry="25.4" fill="url(#plateGrad)" stroke="#1e40af" stroke-width="3"/>
  
  <!-- Internal Map Vector Lines -->
  <path d="M 38 68 C 48 58, 70 74, 90 60" fill="none" stroke="#93c5fd" stroke-width="3.5" stroke-linecap="round"/>
  <path d="M 45 56 C 60 52, 75 58, 85 52" fill="none" stroke="#bfdbfe" stroke-width="2" stroke-linecap="round"/>
  
  <!-- Focus Pin -->
  <circle cx="64" cy="62" r="4" fill="#ffffff" stroke="#1e3a8a" stroke-width="2"/>
</svg>'''
    svg_path = os.path.join(output_dir, "icon.svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Generated {svg_path}")

if __name__ == "__main__":
    generate_icons(os.path.dirname(os.path.abspath(__file__)))
