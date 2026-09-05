# -*- coding: utf-8 -*-
"""Headless tests for axonometric transform math, clipping, extrusion, and sizing."""
import os
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from PyQt5.QtCore import Qt, QSize
    from PyQt5.QtGui import QImage, QPainter, QColor, QPen, QBrush
    from PyQt5.QtWidgets import QApplication
except ImportError:
    from qgis.PyQt.QtCore import Qt, QSize
    from qgis.PyQt.QtGui import QImage, QPainter, QColor, QPen, QBrush
    from qgis.PyQt.QtWidgets import QApplication

from transformer_core import (
    AxoParams, transform_qimage, estimate_output_size, scale_params,
)

app = QApplication.instance() or QApplication(sys.argv)


def make_map(w=800, h=600):
    img = QImage(QSize(w, h), QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor("#f8fafc"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(QColor("#cbd5e1"), 1))
    for x in range(0, w, 50):
        p.drawLine(x, 0, x, h)
    for y in range(0, h, 50):
        p.drawLine(0, y, w, y)
    p.setBrush(QBrush(QColor("#bfdbfe")))
    p.setPen(QPen(QColor("#3b82f6"), 2))
    p.drawRect(80, 60, w - 160, h - 120)
    p.setBrush(QBrush(QColor("#bbf7d0")))
    p.setPen(QPen(QColor("#15803d"), 2))
    p.drawEllipse(w // 2 - 120, h // 2 - 90, 240, 180)
    p.end()
    return img


def alpha_at(img, x, y):
    return img.pixelColor(int(x), int(y)).alpha()


def test_estimate_matches_full():
    src = make_map()
    params = AxoParams(mode="full", padding=12, stroke_width=4, has_extrusion=False)
    out = transform_qimage(src, params)
    ew, eh = estimate_output_size(src.width(), src.height(), params)
    assert out.width() == ew, f"width {out.width()} != estimate {ew}"
    assert out.height() == eh, f"height {out.height()} != estimate {eh}"
    print(f"✓ full plan size {out.width()}×{out.height()} matches estimate")


def test_extrusion_grows_height():
    src = make_map()
    flat = AxoParams(mode="full", padding=12, stroke_width=4, has_extrusion=False)
    slab = AxoParams(mode="full", padding=12, stroke_width=4, has_extrusion=True, extrusion_depth=40)
    a = transform_qimage(src, flat)
    b = transform_qimage(src, slab)
    assert b.height() == a.height() + 40, f"extrusion height {b.height()} vs {a.height()}"
    print("✓ extrusion adds depth to output height")


def test_disc_has_transparent_corners():
    src = make_map(800, 800)
    params = AxoParams(mode="disc", padding=8, stroke_width=4, has_extrusion=False)
    out = transform_qimage(src, params)
    assert alpha_at(out, 1, 1) < 20, "disc corner should be transparent"
    cx, cy = out.width() // 2, int(8 + 2 + (min(800, 800) / 2) * 0.57735)
    assert alpha_at(out, cx, cy) > 200, "disc centre should be opaque"
    print(f"✓ disc clip {out.width()}×{out.height()} (transparent corners)")


def test_layer_mask_clips_and_is_tighter():
    src = make_map(800, 600)
    poly = [(-250, -180), (200, -150), (280, 120), (100, 200), (-220, 160)]
    full = transform_qimage(src, AxoParams(mode="full", padding=16, stroke_width=4))
    mask = transform_qimage(
        src,
        AxoParams(
            mode="layer_mask",
            padding=16,
            stroke_width=4,
            has_extrusion=True,
            extrusion_depth=30,
            frame_polygons=[poly],
            frame_shells=[poly],
        ),
    )
    assert not mask.isNull()
    assert mask.width() < full.width() or mask.height() <= full.height() + 30
    assert alpha_at(mask, 1, 1) < 20
    print(f"✓ layer mask {mask.width()}×{mask.height()} (full was {full.width()}×{full.height()})")


def test_scale_params_and_fallback():
    p = AxoParams(padding=12, stroke_width=4, extrusion_depth=24, mode="layer_mask")
    s = scale_params(p, 0.5)
    assert s.padding == 6
    assert s.stroke_width == 2
    assert s.extrusion_depth == 12
    src = make_map()
    out = transform_qimage(src, AxoParams(mode="layer_mask", frame_polygons=None))
    assert not out.isNull()
    print("✓ scale_params + empty mask fallback")


def test_screen_space_stroke_not_null():
    src = make_map(400, 400)
    out = transform_qimage(src, AxoParams(mode="full", stroke_width=8, padding=4, is_dashed=False))
    # Perimeter of the projected quad should contain some stroke-coloured pixels
    found = False
    target = QColor("#2563eb")
    for y in range(0, out.height(), 3):
        for x in range(0, out.width(), 3):
            c = out.pixelColor(x, y)
            if abs(c.red() - target.red()) < 40 and abs(c.blue() - target.blue()) < 40 and c.alpha() > 80:
                found = True
                break
        if found:
            break
    assert found, "expected isometric perimeter stroke"
    print("✓ screen-space perimeter stroke present")


if __name__ == "__main__":
    test_estimate_matches_full()
    test_extrusion_grows_height()
    test_disc_has_transparent_corners()
    test_layer_mask_clips_and_is_tighter()
    test_scale_params_and_fallback()
    test_screen_space_stroke_not_null()
    print("\n✅ All core transform tests passed")
