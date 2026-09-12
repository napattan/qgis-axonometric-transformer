# -*- coding: utf-8 -*-
"""
Axonometric Map Transformer - Core Projection & Geometry Engine
SSOT implementation matching the thesis axonometric transformer specs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Iterable, List, Optional, Sequence, Tuple

try:
    from qgis.PyQt.QtCore import (
        Qt, QPointF, QRectF, QSize, QSizeF, QMarginsF, QMimeData, QByteArray, QBuffer, QIODevice
    )
    from qgis.PyQt.QtGui import (
        QImage, QPainter, QColor, QPen, QBrush, QPainterPath, QPolygonF, QPdfWriter, QPageSize, QPageLayout
    )
    from qgis.PyQt.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    try:
        from PyQt6.QtCore import (
            Qt, QPointF, QRectF, QSize, QSizeF, QMarginsF, QMimeData, QByteArray, QBuffer, QIODevice
        )
        from PyQt6.QtGui import (
            QImage, QPainter, QColor, QPen, QBrush, QPainterPath, QPolygonF, QPdfWriter, QPageSize, QPageLayout
        )
        from PyQt6.QtWidgets import QApplication
        HAS_QT = True
    except ImportError:
        HAS_QT = False
        QImage = object
        QPainter = object


PROJECTION_PRESETS = {
    "isometric": {
        "name": "Isometric (30°-30°)",
        "ratio": 0.577350269,  # 1 / sqrt(3)
        "description": "Standard 30° architectural axonometric ground plane"
    },
    "dimetric": {
        "name": "Dimetric (2:1)",
        "ratio": 0.500000000,
        "description": "50% vertical compression for high elevation readability"
    },
    "military": {
        "name": "Military / Oblique (45°)",
        "ratio": 0.707106781,  # 1 / sqrt(2)
        "description": "Preserves circular curves at 45° angle"
    },
    "plan_oblique": {
        "name": "True Plan Oblique (1:1)",
        "ratio": 1.000000000,
        "description": "Unsquashed 2D ground rotation"
    }
}

MAX_SAFE_DIM = 8192
Point = Tuple[float, float]
Ring = List[Point]


@dataclass
class AxoParams:
    """Transformation configuration parameters."""
    aspect_ratio: float = 0.577350269
    angle_deg: float = 45.0
    mode: str = "full"  # "full", "disc", "rhombus", or "layer_mask"
    tight_crop: bool = True
    padding: int = 12
    stroke_width: int = 4
    stroke_color: str = "#2563eb"
    is_dashed: bool = True
    has_fill: bool = False
    fill_color: str = "#ffffff"
    fill_opacity: float = 1.0
    has_extrusion: bool = False
    extrusion_depth: int = 24
    extrusion_color: str = "#cbd5e1"
    extrusion_opacity: float = 1.0
    pan_x: int = 0
    pan_y: int = 0
    # Clip rings in source-image space centered at (0, 0). Includes holes.
    frame_polygons: Optional[List[Ring]] = None
    # Exterior shells only (used for 3D extrusion). Falls back to frame_polygons.
    frame_shells: Optional[List[Ring]] = None


def _plan_to_axo(x: float, y: float, cos_a: float, sin_a: float, h_ratio: float) -> Point:
    rx = x * cos_a - y * sin_a
    ry = x * sin_a + y * cos_a
    return rx, ry * h_ratio


def _transform_ring(ring: Sequence[Point], cos_a: float, sin_a: float, h_ratio: float) -> Ring:
    return [_plan_to_axo(x, y, cos_a, sin_a, h_ratio) for x, y in ring]


def _ring_bounds(rings: Iterable[Sequence[Point]]) -> Optional[Tuple[float, float, float, float]]:
    min_u = min_v = float("inf")
    max_u = max_v = float("-inf")
    found = False
    for ring in rings:
        for u, v in ring:
            found = True
            if u < min_u:
                min_u = u
            if u > max_u:
                max_u = u
            if v < min_v:
                min_v = v
            if v > max_v:
                max_v = v
    if not found:
        return None
    return min_u, min_v, max_u, max_v


def _scale_rings(rings: Optional[List[Ring]], scale: float) -> Optional[List[Ring]]:
    if not rings or scale == 1.0:
        return rings
    return [[(x * scale, y * scale) for x, y in ring] for ring in rings]


def scale_params(params: AxoParams, scale: float) -> AxoParams:
    """Scale pixel-space styling and frame geometry for preview / DPI."""
    if scale == 1.0:
        return params
    stroke = 0 if params.stroke_width <= 0 else max(1, int(round(params.stroke_width * scale)))
    return replace(
        params,
        padding=max(0, int(round(params.padding * scale))),
        stroke_width=stroke,
        extrusion_depth=max(1, int(round(params.extrusion_depth * scale))),
        pan_x=int(round(params.pan_x * scale)),
        pan_y=int(round(params.pan_y * scale)),
        frame_polygons=_scale_rings(params.frame_polygons, scale),
        frame_shells=_scale_rings(params.frame_shells, scale),
    )


def _allocate_image(dest_w: int, dest_h: int) -> QImage:
    dest_w = max(10, min(MAX_SAFE_DIM, int(dest_w)))
    dest_h = max(10, min(MAX_SAFE_DIM, int(dest_h)))
    img = QImage(QSize(dest_w, dest_h), QImage.Format.Format_ARGB32_Premultiplied)
    if img.isNull():
        dest_w = max(10, dest_w // 2)
        dest_h = max(10, dest_h // 2)
        img = QImage(QSize(dest_w, dest_h), QImage.Format.Format_ARGB32_Premultiplied)
    if not img.isNull():
        img.fill(Qt.GlobalColor.transparent)
    return img


def _begin_painter(img: QImage) -> QPainter:
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    return painter


def _make_stroke_pen(params: AxoParams) -> QPen:
    pen = QPen(QColor(params.stroke_color), max(1, params.stroke_width))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if params.is_dashed:
        dash_len = max(12, params.stroke_width * 3)
        gap_len = max(8, params.stroke_width * 2)
        width = float(max(1, params.stroke_width))
        pen.setDashPattern([dash_len / width, gap_len / width])
    else:
        pen.setStyle(Qt.PenStyle.SolidLine)
    return pen


def _qpoly(points: Sequence[Point], ox: float = 0.0, oy: float = 0.0) -> QPolygonF:
    poly = QPolygonF()
    for u, v in points:
        poly.append(QPointF(ox + u, oy + v))
    return poly


def _draw_extruded_shells(
    painter: QPainter,
    shells: Sequence[Sequence[Point]],
    cx: float,
    cy: float,
    depth: int,
    ext_col: QColor,
) -> None:
    alpha = ext_col.alpha()
    if depth <= 0 or alpha <= 0:
        return

    edge_pen = QPen(QColor(148, 163, 184, alpha), 1.0)
    edge_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    # Collect front-facing skirts across all shells
    front_skirts = []
    for shell in shells:
        n = len(shell)
        if n < 3:
            continue

        # Signed area to determine winding in screen coordinates (+u right, +v down)
        # Positive = Clockwise, Negative = Counter-Clockwise
        signed_area = sum(
            shell[i][0] * shell[(i + 1) % n][1] - shell[(i + 1) % n][0] * shell[i][1]
            for i in range(n)
        ) / 2.0

        if abs(signed_area) < 1e-6:
            continue
        is_cw = signed_area > 0.0

        for i in range(n):
            u1, v1 = shell[i]
            u2, v2 = shell[(i + 1) % n]
            du = u2 - u1
            dv = v2 - v1
            # In screen space (+u right, +v down):
            # Outward normal for CW is (dv, -du); faces viewer (+v) when -du > 0 <=> du < 0.
            # Outward normal for CCW is (-dv, du); faces viewer (+v) when du > 0.
            is_front = (du < -1e-6) if is_cw else (du > 1e-6)
            if not is_front:
                continue

            # Depth key for Painter's algorithm (render back-to-front: smallest v first)
            mid_v = (v1 + v2) / 2.0
            front_skirts.append((mid_v, u1, v1, u2, v2, du, dv))

    # Sort skirts from furthest to nearest (ascending v) so foreground walls cleanly occlude background walls
    front_skirts.sort(key=lambda s: s[0])

    for _, u1, v1, u2, v2, du, dv in front_skirts:
        seg_angle = math.atan2(dv, du)
        shade = 108 + int(22 * (math.sin(seg_angle) * 0.5 + 0.5))
        skirt = QPolygonF([
            QPointF(cx + u1, cy + v1),
            QPointF(cx + u2, cy + v2),
            QPointF(cx + u2, cy + v2 + depth),
            QPointF(cx + u1, cy + v1 + depth),
        ])
        side_col = ext_col.darker(shade)
        side_col.setAlpha(alpha)
        painter.setBrush(QBrush(side_col))
        painter.setPen(edge_pen)
        painter.drawPolygon(skirt)


def _draw_source_map(
    painter: QPainter,
    src_img: QImage,
    cx: float,
    cy: float,
    h_ratio: float,
    angle_deg: float,
    clip_path: Optional[QPainterPath] = None,
) -> None:
    w = src_img.width()
    h = src_img.height()
    painter.save()
    painter.translate(cx, cy)
    painter.scale(1.0, h_ratio)
    painter.rotate(angle_deg)
    if clip_path is not None:
        painter.setClipPath(clip_path, Qt.ClipOperation.IntersectClip)
    painter.drawImage(QRectF(-w / 2.0, -h / 2.0, float(w), float(h)), src_img)
    painter.restore()


def _path_from_rings(rings: Sequence[Sequence[Point]], cx: float = 0.0, cy: float = 0.0) -> QPainterPath:
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    for ring in rings:
        if len(ring) < 2:
            continue
        path.moveTo(cx + ring[0][0], cy + ring[0][1])
        for u, v in ring[1:]:
            path.lineTo(cx + u, cy + v)
        path.closeSubpath()
    return path


def estimate_output_size(src_w: int, src_h: int, params: AxoParams) -> Tuple[int, int]:
    """Canvas size that transform_qimage would allocate (no painting)."""
    h_ratio = float(params.aspect_ratio)
    angle_rad = math.radians(params.angle_deg)
    pad = params.padding if params.tight_crop else max(params.padding, 40)
    stroke_offset = math.ceil(max(0, params.stroke_width) / 2.0)
    depth = params.extrusion_depth if params.has_extrusion else 0
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    if params.mode in ("disc", "rhombus"):
        rx = min(src_w, src_h) / 2.0
        ry = rx * h_ratio
        dest_w = math.ceil(rx * 2 + stroke_offset * 2 + pad * 2)
        dest_h = math.ceil(ry * 2 + depth + stroke_offset * 2 + pad * 2)
    elif params.mode == "layer_mask" and params.frame_polygons:
        rings = [_transform_ring(r, cos_a, sin_a, h_ratio) for r in params.frame_polygons]
        bounds = _ring_bounds(rings)
        if bounds is None:
            return estimate_output_size(src_w, src_h, replace(params, mode="full", frame_polygons=None))
        min_u, min_v, max_u, max_v = bounds
        dest_w = math.ceil((max_u - min_u) + stroke_offset * 2 + pad * 2)
        dest_h = math.ceil((max_v - min_v) + depth + stroke_offset * 2 + pad * 2)
    else:
        corners = [
            _plan_to_axo(-src_w / 2.0, -src_h / 2.0, cos_a, sin_a, h_ratio),
            _plan_to_axo(src_w / 2.0, -src_h / 2.0, cos_a, sin_a, h_ratio),
            _plan_to_axo(src_w / 2.0, src_h / 2.0, cos_a, sin_a, h_ratio),
            _plan_to_axo(-src_w / 2.0, src_h / 2.0, cos_a, sin_a, h_ratio),
        ]
        min_u, min_v, max_u, max_v = _ring_bounds([corners])
        dest_w = math.ceil((max_u - min_u) + stroke_offset * 2 + pad * 2)
        dest_h = math.ceil((max_v - min_v) + depth + stroke_offset * 2 + pad * 2)

    return max(10, min(MAX_SAFE_DIM, int(dest_w))), max(10, min(MAX_SAFE_DIM, int(dest_h)))


def transform_qimage(src_img: "QImage", params: AxoParams) -> "QImage":
    """
    Transform a QImage into a 3D axonometric / isometric projection.

    Returns a transparent ARGB32_Premultiplied image.
    """
    if not HAS_QT or src_img is None or src_img.isNull():
        return src_img

    w = src_img.width()
    h = src_img.height()
    if w <= 0 or h <= 0:
        return src_img

    h_ratio = float(params.aspect_ratio) if params.aspect_ratio > 0 else 1.0
    angle_rad = math.radians(params.angle_deg)
    pad = params.padding if params.tight_crop else max(params.padding, 40)
    stroke_offset = math.ceil(max(0, params.stroke_width) / 2.0)
    depth = params.extrusion_depth if params.has_extrusion else 0
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    ext_col = QColor(params.extrusion_color)
    ext_alpha = int(round(max(0.0, min(1.0, params.extrusion_opacity)) * 255))
    ext_col.setAlpha(ext_alpha)

    fill_col = QColor(params.fill_color)
    fill_alpha = int(round(max(0.0, min(1.0, params.fill_opacity)) * 255))
    fill_col.setAlpha(fill_alpha)

    mode = params.mode

    if mode == "layer_mask" and not params.frame_polygons:
        return transform_qimage(
            src_img,
            replace(params, mode="full", frame_polygons=None, frame_shells=None),
        )

    painter = None
    try:
        if mode == "full":
            corners = [
                _plan_to_axo(-w / 2.0, -h / 2.0, cos_a, sin_a, h_ratio),
                _plan_to_axo(w / 2.0, -h / 2.0, cos_a, sin_a, h_ratio),
                _plan_to_axo(w / 2.0, h / 2.0, cos_a, sin_a, h_ratio),
                _plan_to_axo(-w / 2.0, h / 2.0, cos_a, sin_a, h_ratio),
            ]
            min_u, min_v, max_u, max_v = _ring_bounds([corners])
            dest_w = int(math.ceil((max_u - min_u) + stroke_offset * 2 + pad * 2))
            dest_h = int(math.ceil((max_v - min_v) + depth + stroke_offset * 2 + pad * 2))
            dest_img = _allocate_image(dest_w, dest_h)
            if dest_img.isNull():
                return src_img

            cx = dest_img.width() / 2.0 + params.pan_x
            cy = pad + stroke_offset + (-min_v) + params.pan_y
            painter = _begin_painter(dest_img)

            if depth > 0:
                _draw_extruded_shells(painter, [corners], cx, cy, depth, ext_col)

            # Solid top cap under map (fill color if fill active, else base plate color if extrusion active)
            top_col = fill_col if (params.has_fill and fill_alpha > 0) else (
                ext_col if (depth > 0 and ext_alpha > 0) else None
            )
            if top_col is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(top_col))
                painter.drawPolygon(_qpoly(corners, cx, cy))

            _draw_source_map(painter, src_img, cx, cy, h_ratio, params.angle_deg)

            if params.stroke_width > 0:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(_make_stroke_pen(params))
                painter.drawPolygon(_qpoly(corners, cx, cy))

            painter.end()
            painter = None
            return dest_img

        if mode in ("disc", "rhombus"):
            rx = min(w, h) / 2.0
            ry = rx * h_ratio
            dest_w = int(math.ceil(rx * 2 + stroke_offset * 2 + pad * 2))
            dest_h = int(math.ceil(ry * 2 + depth + stroke_offset * 2 + pad * 2))
            dest_img = _allocate_image(dest_w, dest_h)
            if dest_img.isNull():
                return src_img

            cx = dest_img.width() / 2.0 + params.pan_x
            cy = pad + stroke_offset + ry + params.pan_y
            painter = _begin_painter(dest_img)

            if depth > 0:
                pen_col = QColor(148, 163, 184, ext_alpha)
                if mode == "disc":
                    bot_col = ext_col.darker(110)
                    bot_col.setAlpha(ext_alpha)
                    painter.setBrush(QBrush(bot_col))
                    painter.setPen(QPen(pen_col, 1.5))
                    painter.drawEllipse(QRectF(cx - rx, cy + depth - ry, rx * 2, ry * 2))

                    skirt_poly = QPolygonF()
                    half = 36
                    for i in range(half, -1, -1):
                        angle = math.pi * i / half
                        skirt_poly.append(QPointF(
                            cx + rx * math.cos(angle),
                            cy + ry * math.sin(angle) + depth,
                        ))
                    for i in range(0, half + 1):
                        angle = math.pi * i / half
                        skirt_poly.append(QPointF(
                            cx + rx * math.cos(angle),
                            cy + ry * math.sin(angle),
                        ))
                    skirt_col = ext_col.darker(120)
                    skirt_col.setAlpha(ext_alpha)
                    painter.setBrush(QBrush(skirt_col))
                    painter.setPen(QPen(pen_col, 1.5))
                    painter.drawPolygon(skirt_poly)

                    bottom_arc = QPainterPath()
                    bottom_rect = QRectF(cx - rx, cy + depth - ry, rx * 2, ry * 2)
                    bottom_arc.arcMoveTo(bottom_rect, 180)
                    bottom_arc.arcTo(bottom_rect, 180, -180)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(QColor(100, 116, 139, ext_alpha), 1.5))
                    painter.drawPath(bottom_arc)
                else:
                    diamond = [
                        (cx, cy - ry),
                        (cx + rx, cy),
                        (cx, cy + ry),
                        (cx - rx, cy),
                    ]
                    bot_col = ext_col
                    bot_col.setAlpha(ext_alpha)
                    painter.setBrush(QBrush(bot_col))
                    painter.setPen(QPen(pen_col, 1.5))
                    painter.drawPolygon(QPolygonF([QPointF(x, y + depth) for x, y in diamond]))

                    r_col = ext_col.darker(115)
                    r_col.setAlpha(ext_alpha)
                    painter.setBrush(QBrush(r_col))
                    painter.drawPolygon(QPolygonF([
                        QPointF(cx, cy + ry),
                        QPointF(cx + rx, cy),
                        QPointF(cx + rx, cy + depth),
                        QPointF(cx, cy + ry + depth),
                    ]))
                    l_col = ext_col.darker(130)
                    l_col.setAlpha(ext_alpha)
                    painter.setBrush(QBrush(l_col))
                    painter.drawPolygon(QPolygonF([
                        QPointF(cx - rx, cy),
                        QPointF(cx, cy + ry),
                        QPointF(cx, cy + ry + depth),
                        QPointF(cx - rx, cy + depth),
                    ]))

            top_col = fill_col if (params.has_fill and fill_alpha > 0) else (
                ext_col if (depth > 0 and ext_alpha > 0) else None
            )
            if top_col is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(top_col))
                if mode == "disc":
                    painter.drawEllipse(QRectF(cx - rx, cy - ry, rx * 2, ry * 2))
                else:
                    painter.drawPolygon(QPolygonF([
                        QPointF(cx, cy - ry),
                        QPointF(cx + rx, cy),
                        QPointF(cx, cy + ry),
                        QPointF(cx - rx, cy),
                    ]))

            clip_path = QPainterPath()
            if mode == "disc":
                clip_path.addEllipse(QRectF(cx - rx, cy - ry, rx * 2, ry * 2))
            else:
                clip_path.addPolygon(QPolygonF([
                    QPointF(cx, cy - ry),
                    QPointF(cx + rx, cy),
                    QPointF(cx, cy + ry),
                    QPointF(cx - rx, cy),
                ]))
            painter.save()
            painter.setClipPath(clip_path)
            _draw_source_map(painter, src_img, cx, cy, h_ratio, params.angle_deg)
            painter.restore()

            if params.stroke_width > 0:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(_make_stroke_pen(params))
                if mode == "disc":
                    painter.drawEllipse(QRectF(cx - rx, cy - ry, rx * 2, ry * 2))
                else:
                    painter.drawPolygon(QPolygonF([
                        QPointF(cx, cy - ry),
                        QPointF(cx + rx, cy),
                        QPointF(cx, cy + ry),
                        QPointF(cx - rx, cy),
                    ]))

            painter.end()
            painter = None
            return dest_img

        if mode == "layer_mask":
            src_rings = [r for r in (params.frame_polygons or []) if r]
            transformed_rings = [_transform_ring(r, cos_a, sin_a, h_ratio) for r in src_rings]
            transformed_rings = [r for r in transformed_rings if r]
            if not transformed_rings:
                return src_img

            bounds = _ring_bounds(transformed_rings)
            if bounds is None:
                return src_img
            min_u, min_v, max_u, max_v = bounds

            max_diag = math.hypot(w, h) * 1.2
            min_u = max(min_u, -max_diag)
            max_u = min(max_u, max_diag)
            min_v = max(min_v, -max_diag)
            max_v = min(max_v, max_diag)

            dest_w = int(math.ceil(max(1.0, max_u - min_u) + stroke_offset * 2 + pad * 2))
            dest_h = int(math.ceil(max(1.0, max_v - min_v) + depth + stroke_offset * 2 + pad * 2))
            dest_img = _allocate_image(dest_w, dest_h)
            if dest_img.isNull():
                return src_img

            cx = pad + stroke_offset + (-min_u) + params.pan_x
            cy = pad + stroke_offset + (-min_v) + params.pan_y
            painter = _begin_painter(dest_img)

            shells_src = params.frame_shells or src_rings
            if depth > 0 and shells_src:
                transformed_shells = [_transform_ring(r, cos_a, sin_a, h_ratio) for r in shells_src if r]
                _draw_extruded_shells(painter, transformed_shells, cx, cy, depth, ext_col)

            top_col = fill_col if (params.has_fill and fill_alpha > 0) else (
                ext_col if (depth > 0 and ext_alpha > 0) else None
            )
            if top_col is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(top_col))
                painter.drawPath(_path_from_rings(transformed_rings, cx, cy))

            local_clip = _path_from_rings(src_rings)
            _draw_source_map(
                painter, src_img, cx, cy, h_ratio, params.angle_deg, clip_path=local_clip
            )

            if params.stroke_width > 0:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(_make_stroke_pen(params))
                painter.drawPath(_path_from_rings(transformed_rings, cx, cy))

            painter.end()
            painter = None
            return dest_img

        return src_img
    finally:
        if painter is not None and painter.isActive():
            painter.end()


def _generate_in_memory_pdf(image: "QImage") -> bytes:
    """Generate an in-memory PDF preserving exact pixel dimensions and alpha transparency (/SMask)."""
    try:
        w, h = image.width(), image.height()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.ReadWrite)
        writer = QPdfWriter(buf)
        writer.setResolution(72)  # 72 DPI: 1 pt = 1 pixel
        page_size = QPageSize(QSizeF(w, h), QPageSize.Unit.Point)
        layout = QPageLayout(
            page_size,
            QPageLayout.Orientation.Portrait,
            QMarginsF(0, 0, 0, 0)
        )
        writer.setPageLayout(layout)

        painter = QPainter(writer)
        painter.drawImage(QRectF(0, 0, w, h), image)
        painter.end()

        pdf_bytes = bytes(buf.data())
        buf.close()
        return pdf_bytes
    except Exception:
        return b""


def _generate_in_memory_svg(image: "QImage", png_bytes: bytes) -> bytes:
    """Generate an in-memory SVG containing embedded 32-bit transparent PNG."""
    try:
        import base64
        w, h = image.width(), image.height()
        b64_png = base64.b64encode(png_bytes).decode('ascii')
        svg_str = (
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<image width="{w}" height="{h}" xlink:href="data:image/png;base64,{b64_png}"/>'
            f'</svg>'
        )
        return svg_str.encode('utf-8')
    except Exception:
        return b""


def _copy_windows_in_memory(png_bytes: bytes, pdf_bytes: bytes, svg_bytes: bytes) -> bool:
    """
    Copy multi-format in-memory bundle to Windows clipboard (PDF + SVG + PNG).
    - Adobe Illustrator: Pastes via native 'Portable Document Format' / 'PDF' as an EMBEDDED object
      with 100% full alpha transparency (no black box, no diagonal 'X').
    - Figma: Pastes via 'image/svg+xml'.
    - Canva, Photoshop, Affinity, Discord, Office: Pastes via 'image/png' / 'PNG'.
    - Zero files on disk, zero CF_HDROP, zero CF_DIB (avoids black background).
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.restype = wintypes.BOOL

        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        GMEM_MOVEABLE = 0x0002

        CF_PDF_FULL = user32.RegisterClipboardFormatW("Portable Document Format")
        CF_PDF = user32.RegisterClipboardFormatW("PDF")
        CF_SVG = user32.RegisterClipboardFormatW("image/svg+xml")
        CF_PNG = user32.RegisterClipboardFormatW("PNG")
        CF_PNG_MIME = user32.RegisterClipboardFormatW("image/png")

        formats_to_set = []
        if pdf_bytes:
            if CF_PDF_FULL:
                formats_to_set.append((CF_PDF_FULL, pdf_bytes))
            if CF_PDF:
                formats_to_set.append((CF_PDF, pdf_bytes))
        if svg_bytes and CF_SVG:
            formats_to_set.append((CF_SVG, svg_bytes))
        if png_bytes:
            if CF_PNG:
                formats_to_set.append((CF_PNG, png_bytes))
            if CF_PNG_MIME:
                formats_to_set.append((CF_PNG_MIME, png_bytes))

        if not user32.OpenClipboard(None):
            return False
        user32.EmptyClipboard()

        for fmt_id, data in formats_to_set:
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if h_mem:
                ptr = kernel32.GlobalLock(h_mem)
                if ptr:
                    ctypes.memmove(ptr, data, len(data))
                    kernel32.GlobalUnlock(h_mem)
                    user32.SetClipboardData(fmt_id, h_mem)

        user32.CloseClipboard()
        return True
    except Exception:
        return False


def copy_image_to_clipboard(image: "QImage", filename_tag: str = "") -> bool:
    """
    Copy a QImage to the OS clipboard as an in-memory multi-format transparent bundle (PDF + SVG + PNG).
    Pastes directly as a 100% transparent EMBEDDED graphic across Adobe Illustrator,
    Photoshop, Affinity Designer, Canva, and Figma without generating any files on disk.
    """
    if not HAS_QT or image is None or image.isNull():
        return False

    export = image
    if image.format() == QImage.Format.Format_ARGB32_Premultiplied:
        export = image.convertToFormat(QImage.Format.Format_ARGB32)

    # 1. In-memory 32-bit PNG bytes
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    export.save(buffer, "PNG")
    buffer.close()
    png_bytes = bytes(byte_array)

    # 2. In-memory PDF bytes (native PDF-1.4 with /SMask 8-bit alpha transparency for Illustrator & Affinity)
    pdf_bytes = _generate_in_memory_pdf(export)

    # 3. In-memory SVG bytes (with embedded base64 32-bit PNG for Figma & vector tools)
    svg_bytes = _generate_in_memory_svg(export, png_bytes)

    # On Windows, inject the multi-format memory bundle (PDF + SVG + PNG, no CF_DIB / no CF_HDROP)
    import sys
    if sys.platform == "win32":
        if _copy_windows_in_memory(png_bytes, pdf_bytes, svg_bytes):
            return True

    # Cross-platform Qt clipboard fallback (macOS, Linux)
    clipboard = QApplication.clipboard()
    if clipboard is None:
        return False

    mime_data = QMimeData()
    if pdf_bytes:
        mime_data.setData("application/pdf", pdf_bytes)
        mime_data.setData("Portable Document Format", pdf_bytes)
        mime_data.setData("PDF", pdf_bytes)
    if svg_bytes:
        mime_data.setData("image/svg+xml", svg_bytes)
    mime_data.setData("PNG", byte_array)
    mime_data.setData("image/png", byte_array)
    mime_data.setData("image/x-png", byte_array)
    mime_data.setData("public.png", byte_array)

    clipboard.setMimeData(mime_data)
    return True
