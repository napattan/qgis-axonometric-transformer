# -*- coding: utf-8 -*-
"""
Verification test for Axonometric Transformer Plugin Layer Mask Framing.
Tests transform_qimage with layer_mask mode, polygon clipping, 3D extrusion, and outline stroke.
"""

import os
import sys
import math

try:
    from PyQt5.QtCore import Qt, QSize, QRectF, QPointF
    from PyQt5.QtGui import QImage, QPainter, QColor, QPen, QBrush, QPolygonF
    from PyQt5.QtWidgets import QApplication
except ImportError:
    from qgis.PyQt.QtCore import Qt, QSize, QRectF, QPointF
    from qgis.PyQt.QtGui import QImage, QPainter, QColor, QPen, QBrush, QPolygonF
    from qgis.PyQt.QtWidgets import QApplication

from transformer_core import AxoParams, transform_qimage

app = QApplication.instance() or QApplication(sys.argv)

def create_test_map_image(w=800, h=600):
    img = QImage(QSize(w, h), QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor("#f8fafc"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    
    # Grid lines
    p.setPen(QPen(QColor("#cbd5e1"), 1))
    for x in range(0, w, 50):
        p.drawLine(x, 0, x, h)
    for y in range(0, h, 50):
        p.drawLine(0, y, w, y)
        
    # Draw some features
    p.setBrush(QBrush(QColor("#bfdbfe")))
    p.setPen(QPen(QColor("#3b82f6"), 2))
    p.drawRect(100, 100, 600, 400)

    p.setBrush(QBrush(QColor("#bbf7d0")))
    p.setPen(QPen(QColor("#15803d"), 2))
    p.drawEllipse(250, 180, 300, 240)
    p.end()
    return img

def test_layer_mask():
    src_img = create_test_map_image(800, 600)
    
    # Define a polygon mask in source image relative coordinates centered at (0, 0)
    # E.g. an irregular site polygon (like On Nut N1_factory)
    poly_rel_pts = [
        (-250, -180),
        ( 200, -150),
        ( 280,  120),
        ( 100,  200),
        (-220,  160)
    ]
    
    params = AxoParams(
        aspect_ratio=0.57735,
        angle_deg=45.0,
        mode="layer_mask",
        tight_crop=True,
        padding=16,
        stroke_width=4,
        stroke_color="#2563eb",
        is_dashed=True,
        has_extrusion=True,
        extrusion_depth=30,
        extrusion_color="#cbd5e1",
        frame_polygons=[poly_rel_pts]
    )
    
    transformed = transform_qimage(src_img, params)
    assert not transformed.isNull(), "Transformed image must not be null"
    assert transformed.width() > 50, f"Transformed width {transformed.width()} too small"
    assert transformed.height() > 50, f"Transformed height {transformed.height()} too small"
    
    output_path = os.path.join(os.path.dirname(__file__), "test_layer_mask_output.png")
    transformed.save(output_path, "PNG")
    print(f"✓ Saved test layer mask result to: {output_path}")
    print(f"✓ Image dimensions: {transformed.width()} x {transformed.height()} px")
    print("✅ Layer mask transformation test passed successfully!")

if __name__ == "__main__":
    test_layer_mask()
