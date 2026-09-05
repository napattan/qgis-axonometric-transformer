# -*- coding: utf-8 -*-
"""
Axonometric Map Transformer - Core Projection & Geometry Engine
SSOT implementation matching the thesis axonometric transformer specs.
"""

import math
from dataclasses import dataclass, replace
from typing import Iterable, List, Optional, Sequence, Tuple

try:
    from qgis.PyQt.QtCore import Qt, QPointF, QRectF, QSize, QMimeData, QByteArray, QBuffer, QIODevice, QUrl
    from qgis.PyQt.QtGui import (
        QImage, QPainter, QColor, QPen, QBrush, QPainterPath, QPolygonF
    )
    from qgis.PyQt.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    try:
        from PyQt5.QtCore import Qt, QPointF, QRectF, QSize, QMimeData, QByteArray, QBuffer, QIODevice, QUrl
        from PyQt5.QtGui import (
            QImage, QPainter, QColor, QPen, QBrush, QPainterPath, QPolygonF
        )
        from PyQt5.QtWidgets import QApplication
        HAS_QT = True
    except ImportError:
        HAS_QT = False


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
    has_extrusion: bool = False
    extrusion_depth: int = 24
    extrusion_color: str = "#cbd5e1"
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
    img = QImage(QSize(dest_w, dest_h), QImage.Format_ARGB32_Premultiplied)
    if img.isNull():
        dest_w = max(10, dest_w // 2)
        dest_h = max(10, dest_h // 2)
        img = QImage(QSize(dest_w, dest_h), QImage.Format_ARGB32_Premultiplied)
    if not img.isNull():
        img.fill(Qt.transparent)
    return img


def _begin_painter(img: QImage) -> QPainter:
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    try:
        painter.setRenderHint(QPainter.HighQualityAntialiasing, True)
    except AttributeError:
        pass
    return painter


def _make_stroke_pen(params: AxoParams) -> QPen:
    pen = QPen(QColor(params.stroke_color), max(1, params.stroke_width))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    if params.is_dashed:
        dash_len = max(12, params.stroke_width * 3)
        gap_len = max(8, params.stroke_width * 2)
        width = float(max(1, params.stroke_width))
        pen.setDashPattern([dash_len / width, gap_len / width])
    else:
        pen.setStyle(Qt.SolidLine)
    return pen


def _qpoly(points: Sequence[Point], ox: float = 0.0, oy: float = 0.0) -> QPolygonF:
    poly = QPolygonF()
    for u, v in points:
        poly.append(QPointF(ox + u, oy + v))
    return poly


def _is_front_edge(u1: float, v1: float, u2: float, v2: float) -> bool:
    """True for walls that face the viewer in a Y-down axonometric view.

    Clockwise footprints (typical GIS image space) have outward +Y when the
    edge travels left-to-right (positive du).
    """
    return (u2 - u1) > 0.0


def _draw_extruded_shells(
    painter: QPainter,
    shells: Sequence[Sequence[Point]],
    cx: float,
    cy: float,
    depth: int,
    ext_col: QColor,
) -> None:
    edge_pen = QPen(QColor("#94a3b8"), 1.0)
    edge_pen.setJoinStyle(Qt.RoundJoin)
    bottom_pen = QPen(QColor("#94a3b8"), 1.2)
    bottom_pen.setJoinStyle(Qt.RoundJoin)

    for shell in shells:
        if len(shell) < 3:
            continue
        painter.setBrush(QBrush(ext_col.darker(110)))
        painter.setPen(bottom_pen)
        painter.drawPolygon(_qpoly(shell, cx, cy + depth))

        n = len(shell)
        for i in range(n):
            u1, v1 = shell[i]
            u2, v2 = shell[(i + 1) % n]
            if not _is_front_edge(u1, v1, u2, v2):
                continue
            du = u2 - u1
            dv = v2 - v1
            seg_angle = math.atan2(dv, du)
            shade = 108 + int(22 * (math.sin(seg_angle) * 0.5 + 0.5))
            skirt = QPolygonF([
                QPointF(cx + u1, cy + v1),
                QPointF(cx + u2, cy + v2),
                QPointF(cx + u2, cy + v2 + depth),
                QPointF(cx + u1, cy + v1 + depth),
            ])
            painter.setBrush(QBrush(ext_col.darker(shade)))
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
        painter.setClipPath(clip_path, Qt.IntersectClip)
    painter.drawImage(QRectF(-w / 2.0, -h / 2.0, float(w), float(h)), src_img)
    painter.restore()


def _path_from_rings(rings: Sequence[Sequence[Point]], cx: float = 0.0, cy: float = 0.0) -> QPainterPath:
    path = QPainterPath()
    path.setFillRule(Qt.OddEvenFill)
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

            _draw_source_map(painter, src_img, cx, cy, h_ratio, params.angle_deg)

            if params.stroke_width > 0:
                painter.setBrush(Qt.NoBrush)
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
                if mode == "disc":
                    painter.setBrush(QBrush(ext_col.darker(110)))
                    painter.setPen(QPen(QColor("#94a3b8"), 1.5))
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
                    painter.setBrush(QBrush(ext_col.darker(120)))
                    painter.setPen(QPen(QColor("#94a3b8"), 1.5))
                    painter.drawPolygon(skirt_poly)

                    bottom_arc = QPainterPath()
                    bottom_rect = QRectF(cx - rx, cy + depth - ry, rx * 2, ry * 2)
                    bottom_arc.arcMoveTo(bottom_rect, 180)
                    bottom_arc.arcTo(bottom_rect, 180, -180)
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(QPen(QColor("#64748b"), 1.5))
                    painter.drawPath(bottom_arc)
                else:
                    diamond = [
                        (cx, cy - ry),
                        (cx + rx, cy),
                        (cx, cy + ry),
                        (cx - rx, cy),
                    ]
                    painter.setBrush(QBrush(ext_col))
                    painter.setPen(QPen(QColor("#94a3b8"), 1.5))
                    painter.drawPolygon(QPolygonF([QPointF(x, y + depth) for x, y in diamond]))

                    painter.setBrush(QBrush(ext_col.darker(115)))
                    painter.drawPolygon(QPolygonF([
                        QPointF(cx, cy + ry),
                        QPointF(cx + rx, cy),
                        QPointF(cx + rx, cy + depth),
                        QPointF(cx, cy + ry + depth),
                    ]))
                    painter.setBrush(QBrush(ext_col.darker(130)))
                    painter.drawPolygon(QPolygonF([
                        QPointF(cx - rx, cy),
                        QPointF(cx, cy + ry),
                        QPointF(cx, cy + ry + depth),
                        QPointF(cx - rx, cy + depth),
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
                painter.setBrush(Qt.NoBrush)
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

            local_clip = _path_from_rings(src_rings)
            _draw_source_map(
                painter, src_img, cx, cy, h_ratio, params.angle_deg, clip_path=local_clip
            )

            if params.stroke_width > 0:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(_make_stroke_pen(params))
                painter.drawPath(_path_from_rings(transformed_rings, cx, cy))

            painter.end()
            painter = None
            return dest_img

        return src_img
    finally:
        if painter is not None and painter.isActive():
            painter.end()


def copy_image_to_clipboard(image: "QImage") -> bool:
    """Copy a QImage to the OS clipboard as transparent PNG (bypassing Windows CF_DIB black box in Illustrator)."""
    if not HAS_QT or image is None or image.isNull():
        return False
    clipboard = QApplication.clipboard()
    if clipboard is None:
        return False

    export = image
    if image.format() == QImage.Format_ARGB32_Premultiplied:
        export = image.convertToFormat(QImage.Format_ARGB32)

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.WriteOnly)
    export.save(buffer, "PNG")
    buffer.close()

    mime_data = QMimeData()
    # NOTE: DO NOT call mime_data.setImageData(export)!
    # On Windows, setImageData registers legacy CF_DIB GDI bitmap which strips alpha channels and renders black in Illustrator.
    # By registering only 32-bit PNG mime and CF_HDROP file URL, Illustrator and Affinity import the native transparent PNG!
    mime_data.setData("PNG", byte_array)
    mime_data.setData("image/png", byte_array)
    mime_data.setData("image/x-png", byte_array)
    mime_data.setData("public.png", byte_array)

    try:
        import tempfile
        import os
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "qgis_axonometric_clipboard.png")
        export.save(temp_path, "PNG")
        mime_data.setUrls([QUrl.fromLocalFile(temp_path)])
    except (OSError, AttributeError):
        pass

    clipboard.setMimeData(mime_data)
    return True
