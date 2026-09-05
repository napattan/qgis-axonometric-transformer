# -*- coding: utf-8 -*-
"""Test disc base plate rendering in PyQt/QPainter."""
import sys
try:
    from qgis.PyQt.QtCore import Qt, QRectF, QPointF, QSize
    from qgis.PyQt.QtGui import QImage, QPainter, QPainterPath, QColor, QPen, QBrush, QPolygonF
    from qgis.PyQt.QtWidgets import QApplication
except ImportError:
    from PyQt6.QtCore import Qt, QRectF, QPointF, QSize
    from PyQt6.QtGui import QImage, QPainter, QPainterPath, QColor, QPen, QBrush, QPolygonF
    from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

cx = 300
cy = 200
rx = 200
ry = 200 * 0.57735  # ~115.47
depth = 40

img = QImage(600, 500, QImage.Format.Format_ARGB32_Premultiplied)
img.fill(Qt.GlobalColor.transparent)

painter = QPainter(img)
painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

ext_col = QColor("#cbd5e1")

# 1. Cylinder Base Skirt Path
# In Qt:
# 0 deg = 3 o'clock (Right)
# 90 deg = 12 o'clock (Top)
# 180 deg = 9 o'clock (Left)
# 270 deg = 6 o'clock (Bottom)
# To sweep through bottom from 180 to 0 (left to right): start 180, sweep -180 (or start 180, sweep 180 in reversed angle system)
# Let's verify Qt arcTo: startAngle in degrees, sweepLength in degrees (positive = counterclockwise, negative = clockwise)
# Since screen Y is down:
# Clockwise (negative sweep) goes from 180 (left) through 270 (bottom) to 0 (right).
# Counterclockwise (positive sweep) goes from 180 (left) through 90 (top) to 0 (right).

skirt_path = QPainterPath()
skirt_path.moveTo(cx - rx, cy)
skirt_path.lineTo(cx - rx, cy + depth)
# Arc at bottom level: left (180) to right (0) through bottom (clockwise = -180 deg)
skirt_path.arcTo(QRectF(cx - rx, cy + depth - ry, rx * 2, ry * 2), 180, -180)
skirt_path.lineTo(cx + rx, cy)
# Arc at top level: right (0) to left (180) through bottom (counterclockwise = +180 deg, or clockwise back?)
# To go back to start (cx - rx, cy) through bottom: start 0, sweep 180 (counter-clockwise goes through top, which closes the upper edge!)
skirt_path.arcTo(QRectF(cx - rx, cy - ry, rx * 2, ry * 2), 0, 180)
skirt_path.closeSubpath()

# Fill skirt
painter.setBrush(QBrush(ext_col.darker(115)))
painter.setPen(QPen(QColor("#94a3b8"), 2.0))
painter.drawPath(skirt_path)

# Draw bottom rim outline
bottom_rim = QPainterPath()
bottom_rim.arcMoveTo(QRectF(cx - rx, cy + depth - ry, rx * 2, ry * 2), 180)
bottom_rim.arcTo(QRectF(cx - rx, cy + depth - ry, rx * 2, ry * 2), 180, -180)
painter.setBrush(Qt.BrushStyle.NoBrush)
painter.setPen(QPen(QColor("#64748b"), 2.0))
painter.drawPath(bottom_rim)

# Top ellipse (Map or disc top)
top_clip = QPainterPath()
top_clip.addEllipse(QRectF(cx - rx, cy - ry, rx * 2, ry * 2))

painter.setBrush(QBrush(QColor("#93c5fd")))
painter.setPen(QPen(QColor("#2563eb"), 4.0))
painter.drawPath(top_clip)

painter.end()

img.save("test_disc_base.png", "PNG")
print("Saved test_disc_base.png")
