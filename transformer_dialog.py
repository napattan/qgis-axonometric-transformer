# -*- coding: utf-8 -*-
"""
Axonometric Map Transformer - Interactive QGIS Dialog
Provides real-time interactive preview, source selection (Canvas/Bookmark/Layout/Layer),
projection tweaking, 3D architectural base plate styling, and 1-click clipboard/file export.
"""

import os
import tempfile
from typing import Optional, List, Dict, Tuple

from qgis.PyQt.QtCore import Qt, QSize, QRectF, QPointF, QTimer
from qgis.PyQt.QtGui import (
    QImage, QPixmap, QPainter, QColor, QPen, QBrush, QKeySequence
)
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QSpinBox, QCheckBox, QColorDialog, QFileDialog,
    QGroupBox, QWidget, QScrollArea, QFrame, QSplitter,
    QMessageBox, QToolTip, QSizePolicy, QApplication, QListView
)

from qgis.core import (
    QgsProject, QgsApplication, QgsMapSettings, QgsMapRendererCustomPainterJob,
    QgsRectangle, QgsVectorLayer, QgsLayoutItemPicture, QgsLayoutPoint,
    QgsLayoutSize, QgsUnitTypes, QgsLayoutExporter, QgsCoordinateTransform,
    QgsBookmark, QgsGeometry, QgsWkbTypes, QgsCoordinateReferenceSystem,
    QgsFeatureRequest, QgsLayoutItemMap, QgsLayerTreeGroup, QgsLayerTreeLayer
)

try:
    from .transformer_core import (
        AxoParams, PROJECTION_PRESETS, transform_qimage, copy_image_to_clipboard,
        scale_params, estimate_output_size
    )
except ImportError:
    from transformer_core import (
        AxoParams, PROJECTION_PRESETS, transform_qimage, copy_image_to_clipboard,
        scale_params, estimate_output_size
    )

PREVIEW_MAX_EDGE = 1600
MAX_CAPTURE_EDGE = 8192
COPY_BTN_STYLE = """
    QPushButton {
        background-color: #2563eb;
        color: white;
        font-weight: 700;
        font-size: 13px;
        padding: 10px 16px;
        border-radius: 6px;
        border: none;
    }
    QPushButton:hover {
        background-color: #1d4ed8;
    }
"""
COPY_BTN_DONE_STYLE = (
    "background-color: #059669; color: white; font-weight: 700; "
    "font-size: 13px; padding: 10px 16px; border-radius: 6px; border: none;"
)


class AspectRatioPixmapLabel(QLabel):
    """Interactive preview label that scales pixmaps smoothly maintaining aspect ratio."""
    _READY_STYLE = (
        "background-color: #f1f5f9; border: 1px dashed #cbd5e1; border-radius: 8px;"
    )
    _EMPTY_STYLE = (
        "background-color: #f8fafc; color: #64748b; font-size: 12px; "
        "border: 1px dashed #cbd5e1; border-radius: 8px;"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(self._READY_STYLE)
        self._pixmap = QPixmap()
        self._fitted = QPixmap()
        self._fitted_for = QSize()

    def set_transformed_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self._fitted = QPixmap()
        self._fitted_for = QSize()
        self.update_display()

    def update_display(self):
        if self._pixmap.isNull():
            self.setText("No map rendered yet.\nClick 'Capture / Re-Render Map' to begin.")
            self.setStyleSheet(self._EMPTY_STYLE)
            return

        target = self.size()
        if self._fitted_for == target and not self._fitted.isNull():
            self.setPixmap(self._fitted)
            return

        scaled = self._pixmap.scaled(
            target,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self._fitted = scaled
        self._fitted_for = QSize(target)
        self.setStyleSheet(self._READY_STYLE)
        self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_display()


class AxonometricTransformerDialog(QDialog):
    """Main Interactive Dialog for QGIS Axonometric Transformer."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.raw_source_image = QImage()
        self.transformed_image = QImage()
        self.params = AxoParams()
        self.bookmarks_map: Dict[str, QgsBookmark] = {}
        self.last_render_extent: Optional[QgsRectangle] = None
        self.last_render_crs = None
        self.last_render_size = QSize(0, 0)
        self.cached_frame_polygons: Optional[List[List[Tuple[float, float]]]] = None
        self.cached_frame_shells: Optional[List[List[Tuple[float, float]]]] = None
        self.cached_frame_layer_id: Optional[str] = None
        self.cached_frame_selected_only: bool = False
        self.cached_render_extent = None
        self._output_scale = 2
        self._export_image = QImage()
        self._export_dirty = True
        self._capturing = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(40)
        self._preview_timer.timeout.connect(self._run_preview)

        self.setWindowTitle("Axonometric Map Transformer — 3D Isometric & Axo Plan Generator")
        self.resize(1100, 750)
        self.setMinimumSize(850, 600)

        self._setup_ui()
        self._populate_layers_and_layouts()
        self.capture_source_image()

    def _setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(12, 12, 12, 12)
        self.main_layout.setSpacing(12)

        # Splitter between controls and preview
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.main_layout.addWidget(self.splitter)

        # -------------------------------------------------------------
        # LEFT PANEL: Controls (Scrollable)
        # -------------------------------------------------------------
        self.left_scroll = QScrollArea(self.splitter)
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setFrameShape(QFrame.NoFrame)
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.left_scroll.setMinimumWidth(380)
        self.left_scroll.setMaximumWidth(460)

        self.left_widget = QWidget(self.left_scroll)
        self.left_widget.setMaximumWidth(444)
        self.left_layout = QVBoxLayout(self.left_widget)
        self.left_layout.setContentsMargins(4, 4, 8, 4)
        self.left_layout.setSpacing(12)

        # --- Section 1: Source Selection & Resolution ---
        self.grp_source = QGroupBox("1. Map Source && Resolution", self.left_widget)
        layout_source = QVBoxLayout(self.grp_source)

        h_src_type = QHBoxLayout()
        h_src_type.addWidget(QLabel("Source:", self.grp_source))
        self.combo_source_type = QComboBox(self.grp_source)
        self.combo_source_type.addItems([
            "Active Map Canvas",
            "Spatial Bookmark",
            "Selected Layer Extent",
            "QGIS Print Layout"
        ])
        self.combo_source_type.currentIndexChanged.connect(self._on_source_type_changed)
        h_src_type.addWidget(self.combo_source_type, 1)
        layout_source.addLayout(h_src_type)

        # Dynamic Dropdowns
        self.combo_bookmark = QComboBox(self.grp_source)
        self.combo_bookmark.setVisible(False)
        self.combo_bookmark.currentIndexChanged.connect(self.capture_source_image)
        layout_source.addWidget(self.combo_bookmark)

        self.combo_layer = QComboBox(self.grp_source)
        self.combo_layer.setVisible(False)
        self.combo_layer.currentIndexChanged.connect(self.capture_source_image)
        layout_source.addWidget(self.combo_layer)

        self.combo_layout = QComboBox(self.grp_source)
        self.combo_layout.setVisible(False)
        self.combo_layout.currentIndexChanged.connect(self.capture_source_image)
        layout_source.addWidget(self.combo_layout)

        # Resolution & Transparency
        h_res = QHBoxLayout()
        h_res.addWidget(QLabel("Quality:", self.grp_source))
        self.combo_res = QComboBox(self.grp_source)
        self.combo_res.addItem("Screen Res (1x)", 1)
        self.combo_res.addItem("High-DPI (150 DPI / 2x)", 2)
        self.combo_res.addItem("Print Ready (300 DPI / 4x)", 4)
        self.combo_res.setCurrentIndex(1)
        self.combo_res.currentIndexChanged.connect(self.capture_source_image)
        h_res.addWidget(self.combo_res, 1)
        layout_source.addLayout(h_res)

        self.chk_transparent = QCheckBox("Transparent Background (Alpha)", self.grp_source)
        self.chk_transparent.setChecked(True)
        self.chk_transparent.toggled.connect(self.capture_source_image)
        layout_source.addWidget(self.chk_transparent)

        btn_capture = QPushButton("🔄 Capture / Re-Render Map", self.grp_source)
        btn_capture.setStyleSheet("font-weight: 600; padding: 6px; background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; border-radius: 4px;")
        btn_capture.clicked.connect(self.capture_source_image)
        layout_source.addWidget(btn_capture)

        self.left_layout.addWidget(self.grp_source)

        # --- Section 2: Axonometric Standard & Orientation ---
        self.grp_proj = QGroupBox("2. Projection Standard && Orientation", self.left_widget)
        layout_proj = QVBoxLayout(self.grp_proj)

        # Preset Buttons
        h_presets = QHBoxLayout()
        self.btn_iso = QPushButton("Isometric (30°)", self.grp_proj)
        self.btn_dim = QPushButton("Dimetric (2:1)", self.grp_proj)
        self.btn_mil = QPushButton("Military (45°)", self.grp_proj)
        
        for btn in (self.btn_iso, self.btn_dim, self.btn_mil):
            btn.setCheckable(True)
            h_presets.addWidget(btn)

        self.btn_iso.setChecked(True)
        self.btn_iso.clicked.connect(lambda: self._set_preset("isometric"))
        self.btn_dim.clicked.connect(lambda: self._set_preset("dimetric"))
        self.btn_mil.clicked.connect(lambda: self._set_preset("military"))
        layout_proj.addLayout(h_presets)

        # Custom Height Ratio Slider
        h_ratio = QHBoxLayout()
        h_ratio.addWidget(QLabel("Height Squash:", self.grp_proj))
        self.slider_ratio = QSlider(Qt.Horizontal, self.grp_proj)
        self.slider_ratio.setRange(20, 100)
        self.slider_ratio.setValue(int(self.params.aspect_ratio * 100))
        self.slider_ratio.valueChanged.connect(self._on_ratio_slider_changed)
        self.lbl_ratio_val = QLabel(f"{int(self.params.aspect_ratio * 100)}%", self.grp_proj)
        self.lbl_ratio_val.setFixedWidth(45)
        h_ratio.addWidget(self.slider_ratio, 1)
        h_ratio.addWidget(self.lbl_ratio_val)
        layout_proj.addLayout(h_ratio)

        # Orientation Angle
        h_angle = QHBoxLayout()
        h_angle.addWidget(QLabel("Plan Orientation:", self.grp_proj))
        self.slider_angle = QSlider(Qt.Horizontal, self.grp_proj)
        self.slider_angle.setRange(-180, 180)
        self.slider_angle.setValue(45)
        self.slider_angle.valueChanged.connect(self._on_angle_changed)
        self.lbl_angle_val = QLabel("45°", self.grp_proj)
        self.lbl_angle_val.setFixedWidth(45)
        h_angle.addWidget(self.slider_angle, 1)
        h_angle.addWidget(self.lbl_angle_val)
        layout_proj.addLayout(h_angle)

        # Angle Quick Chips
        h_chips = QHBoxLayout()
        for deg in (-45, 0, 45, 90):
            btn_chip = QPushButton(f"{deg}°" if deg != 0 else "0° (North)", self.grp_proj)
            btn_chip.setStyleSheet("padding: 2px 6px; font-size: 11px;")
            btn_chip.clicked.connect(lambda checked, d=deg: self.slider_angle.setValue(d))
            h_chips.addWidget(btn_chip)
        layout_proj.addLayout(h_chips)

        self.left_layout.addWidget(self.grp_proj)

        # --- Section 3: Framing & Architectural Base Plate ---
        self.grp_frame = QGroupBox("3. Bounding Framing && 3D Plate", self.left_widget)
        layout_frame = QVBoxLayout(self.grp_frame)

        h_mode = QHBoxLayout()
        h_mode.addWidget(QLabel("Framing Mode:", self.grp_frame))
        self.combo_mode = QComboBox(self.grp_frame)
        self.combo_mode.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_mode.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_mode.setMinimumContentsLength(18)
        self.combo_mode.addItem("🖼️ Full Plan / Tight Box", "full")
        self.combo_mode.addItem("⭕ Circular Site Disc", "disc")
        self.combo_mode.addItem("🔷 Isometric Diamond", "rhombus")
        self.combo_mode.addItem("📐 Vector Layer Boundary / Mask", "layer_mask")
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        h_mode.addWidget(self.combo_mode, 1)
        layout_frame.addLayout(h_mode)

        # Container for Vector Layer Mask Options (visible when mode == 'layer_mask')
        self.widget_frame_layer = QWidget(self.grp_frame)
        self.widget_frame_layer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        layout_frame_layer = QVBoxLayout(self.widget_frame_layer)
        layout_frame_layer.setContentsMargins(0, 4, 0, 4)
        layout_frame_layer.setSpacing(6)

        h_fl = QHBoxLayout()
        h_fl.addWidget(QLabel("Frame Layer:", self.widget_frame_layer))
        self.combo_frame_layer = QComboBox(self.widget_frame_layer)
        self.combo_frame_layer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_frame_layer.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_frame_layer.setMinimumContentsLength(18)
        self.combo_frame_layer.setMinimumWidth(80)
        self.combo_frame_layer.setMaxVisibleItems(32)
        self.combo_frame_layer.setToolTip("Polygon layers only — points and lines cannot be used as a mask.")
        # Native macOS combo menus clip long lists; a list view scrolls.
        frame_layer_view = QListView(self.combo_frame_layer)
        frame_layer_view.setUniformItemSizes(True)
        self.combo_frame_layer.setView(frame_layer_view)
        self.combo_frame_layer.currentIndexChanged.connect(self._on_frame_layer_changed)
        h_fl.addWidget(self.combo_frame_layer, 1)

        btn_refresh_fl = QPushButton("🔄", self.widget_frame_layer)
        btn_refresh_fl.setToolTip("Refresh layers list")
        btn_refresh_fl.setFixedSize(28, 28)
        btn_refresh_fl.clicked.connect(self._populate_frame_layers)
        h_fl.addWidget(btn_refresh_fl)
        layout_frame_layer.addLayout(h_fl)

        self.chk_frame_selected_only = QCheckBox("Selected Feature(s) Only", self.widget_frame_layer)
        self.chk_frame_selected_only.setChecked(False)
        self.chk_frame_selected_only.toggled.connect(self._on_frame_layer_changed)
        layout_frame_layer.addWidget(self.chk_frame_selected_only)

        btn_fit_extent = QPushButton("🔍 Fit Extent to Layer", self.widget_frame_layer)
        btn_fit_extent.setToolTip("Set map source extent to this framing layer and capture")
        btn_fit_extent.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_fit_extent.setStyleSheet(
            "padding: 4px 8px; font-size: 11px; background: #f0fdf4; "
            "color: #15803d; border: 1px solid #bbf7d0; border-radius: 3px;"
        )
        btn_fit_extent.clicked.connect(self._fit_source_to_frame_layer)
        layout_frame_layer.addWidget(btn_fit_extent)

        self.widget_frame_layer.setVisible(False)
        layout_frame.addWidget(self.widget_frame_layer)

        self.chk_tight = QCheckBox("Tight Bounding Frame (No Blank Margins)", self.grp_frame)
        self.chk_tight.setChecked(True)
        self.chk_tight.toggled.connect(self._update_render)
        layout_frame.addWidget(self.chk_tight)

        # Padding
        h_pad = QHBoxLayout()
        h_pad.addWidget(QLabel("Padding (px @ 1×):", self.grp_frame))
        self.spin_pad = QSpinBox(self.grp_frame)
        self.spin_pad.setRange(0, 100)
        self.spin_pad.setValue(12)
        self.spin_pad.valueChanged.connect(self._update_render)
        h_pad.addWidget(self.spin_pad)
        layout_frame.addLayout(h_pad)

        # Stroke Outline
        h_stroke = QHBoxLayout()
        self.chk_stroke = QCheckBox("Perimeter Outline", self.grp_frame)
        self.chk_stroke.setChecked(True)
        self.chk_stroke.toggled.connect(self._update_render)
        h_stroke.addWidget(self.chk_stroke)

        self.spin_stroke = QSpinBox(self.grp_frame)
        self.spin_stroke.setRange(1, 30)
        self.spin_stroke.setValue(4)
        self.spin_stroke.valueChanged.connect(self._update_render)
        h_stroke.addWidget(self.spin_stroke)

        self.btn_stroke_col = QPushButton(self.grp_frame)
        self.btn_stroke_col.setFixedSize(24, 24)
        self.btn_stroke_col.setStyleSheet(f"background-color: {self.params.stroke_color}; border: 1px solid #64748b; border-radius: 3px;")
        self.btn_stroke_col.clicked.connect(self._pick_stroke_color)
        h_stroke.addWidget(self.btn_stroke_col)

        self.chk_dashed = QCheckBox("Dashed", self.grp_frame)
        self.chk_dashed.setChecked(True)
        self.chk_dashed.toggled.connect(self._update_render)
        h_stroke.addWidget(self.chk_dashed)
        layout_frame.addLayout(h_stroke)

        # 3D Extrusion Slab
        h_ext = QHBoxLayout()
        self.chk_extrusion = QCheckBox("3D Architectural Base Plate", self.grp_frame)
        self.chk_extrusion.setChecked(False)
        self.chk_extrusion.toggled.connect(self._update_render)
        h_ext.addWidget(self.chk_extrusion)

        self.spin_depth = QSpinBox(self.grp_frame)
        self.spin_depth.setRange(4, 150)
        self.spin_depth.setValue(24)
        self.spin_depth.setSuffix(" px")
        self.spin_depth.valueChanged.connect(self._update_render)
        h_ext.addWidget(self.spin_depth)

        self.btn_ext_col = QPushButton(self.grp_frame)
        self.btn_ext_col.setFixedSize(24, 24)
        self.btn_ext_col.setStyleSheet(f"background-color: {self.params.extrusion_color}; border: 1px solid #64748b; border-radius: 3px;")
        self.btn_ext_col.clicked.connect(self._pick_extrusion_color)
        h_ext.addWidget(self.btn_ext_col)
        layout_frame.addLayout(h_ext)

        # Reset button at bottom of left panel
        btn_reset_left = QPushButton("🔄 Reset All Settings to Default", self.left_widget)
        btn_reset_left.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                font-weight: 600;
                font-size: 11px;
                padding: 6px 10px;
                border-radius: 4px;
                border: 1px solid #cbd5e1;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
                color: #1e293b;
            }
        """)
        btn_reset_left.clicked.connect(self.reset_to_defaults)
        self.left_layout.addWidget(self.grp_frame)
        self.left_layout.addWidget(btn_reset_left)
        self.left_layout.addStretch(1)

        self.left_scroll.setWidget(self.left_widget)
        self.splitter.addWidget(self.left_scroll)

        # -------------------------------------------------------------
        # RIGHT PANEL: Live Interactive Preview & Action Buttons
        # -------------------------------------------------------------
        self.right_widget = QWidget(self.splitter)
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_layout.setContentsMargins(8, 4, 4, 4)
        self.right_layout.setSpacing(10)

        # Preview Header / Stats
        h_prev_header = QHBoxLayout()
        self.lbl_stats = QLabel("Ready", self.right_widget)
        self.lbl_stats.setStyleSheet("font-weight: 600; color: #1e293b; font-size: 12px;")
        h_prev_header.addWidget(self.lbl_stats)
        h_prev_header.addStretch(1)

        btn_reset_hdr = QPushButton("🔄 Reset", self.right_widget)
        btn_reset_hdr.setStyleSheet("padding: 2px 8px; font-size: 11px; font-weight: 600; color: #64748b; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px;")
        btn_reset_hdr.clicked.connect(self.reset_to_defaults)
        h_prev_header.addWidget(btn_reset_hdr)

        self.right_layout.addLayout(h_prev_header)

        # Preview Canvas Display
        self.preview_label = AspectRatioPixmapLabel(self.right_widget)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.right_layout.addWidget(self.preview_label, 1)

        # Action Buttons
        h_actions = QHBoxLayout()
        h_actions.setSpacing(8)
        
        # Primary Action: Copy to Clipboard
        self.btn_copy = QPushButton("📋 Copy to Clipboard (Cmd/Ctrl+C)", self.right_widget)
        self.btn_copy.setStyleSheet(COPY_BTN_STYLE)
        self.btn_copy.setShortcut(QKeySequence.Copy)
        self.btn_copy.setToolTip("Copy the full-resolution axonometric PNG (with alpha) to the clipboard")
        self.btn_copy.clicked.connect(self._on_copy_to_clipboard)
        h_actions.addWidget(self.btn_copy, 2)

        # Save High-Res PNG
        self.btn_save = QPushButton("💾 Save PNG...", self.right_widget)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #f8fafc;
                color: #1e293b;
                font-weight: 600;
                font-size: 12px;
                padding: 10px 14px;
                border-radius: 6px;
                border: 1px solid #cbd5e1;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
        """)
        self.btn_save.clicked.connect(self._on_save_png)
        h_actions.addWidget(self.btn_save, 1)

        # Add to Layout
        self.btn_to_layout = QPushButton("🖼️ Insert into Layout", self.right_widget)
        self.btn_to_layout.setStyleSheet("""
            QPushButton {
                background-color: #f8fafc;
                color: #1e293b;
                font-weight: 600;
                font-size: 12px;
                padding: 10px 14px;
                border-radius: 6px;
                border: 1px solid #cbd5e1;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
        """)
        self.btn_to_layout.clicked.connect(self._on_insert_into_layout)
        h_actions.addWidget(self.btn_to_layout, 1)

        self.right_layout.addLayout(h_actions)
        self.splitter.addWidget(self.right_widget)

        # Set initial splitter ratio (40% left, 60% right)
        self.splitter.setSizes([420, 680])

    def refresh_project_lists(self):
        """Refresh dropdowns from the open project without recapturing the map."""
        self._populate_layers_and_layouts()

    def _populate_layers_and_layouts(self):
        """Populate layer, layout, and spatial bookmark dropdowns from active QGIS project."""
        prev_bm = self.combo_bookmark.currentData() if hasattr(self, "combo_bookmark") else None
        prev_layer = self.combo_layer.currentData() if hasattr(self, "combo_layer") else None
        prev_layout = self.combo_layout.currentData() if hasattr(self, "combo_layout") else None

        # 1. Bookmarks
        self.bookmarks_map = {}
        self.combo_bookmark.blockSignals(True)
        self.combo_bookmark.clear()
        try:
            proj_mgr = QgsProject.instance().bookmarkManager()
            app_mgr = QgsApplication.bookmarkManager()
            all_bms = list(proj_mgr.bookmarks()) + list(app_mgr.bookmarks())
            for bm in all_bms:
                bm_id = bm.id()
                bm_name = bm.name() or "Unnamed Bookmark"
                self.combo_bookmark.addItem(f"📌 {bm_name}", bm_id)
                self.bookmarks_map[bm_id] = bm
        except Exception:
            pass

        if self.combo_bookmark.count() == 0:
            self.combo_bookmark.addItem("No Bookmarks Found", "")
        elif prev_bm:
            idx = self.combo_bookmark.findData(prev_bm)
            if idx >= 0:
                self.combo_bookmark.setCurrentIndex(idx)
        self.combo_bookmark.blockSignals(False)

        # 2. Layers
        self.combo_layer.blockSignals(True)
        self.combo_layer.clear()
        for layer_id, layer in QgsProject.instance().mapLayers().items():
            self.combo_layer.addItem(layer.name(), layer_id)
        if prev_layer:
            idx = self.combo_layer.findData(prev_layer)
            if idx >= 0:
                self.combo_layer.setCurrentIndex(idx)
        self.combo_layer.blockSignals(False)

        # 3. Layouts
        self.combo_layout.blockSignals(True)
        self.combo_layout.clear()
        layout_manager = QgsProject.instance().layoutManager()
        for layout in layout_manager.printLayouts():
            self.combo_layout.addItem(layout.name(), layout.name())
        if prev_layout:
            idx = self.combo_layout.findData(prev_layout)
            if idx >= 0:
                self.combo_layout.setCurrentIndex(idx)
        self.combo_layout.blockSignals(False)

        # 4. Framing Vector Layers
        self._populate_frame_layers()

    @staticmethod
    def _is_polygon_layer(layer):
        """True for polygon / multipolygon / curve-polygon vectors only."""
        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            return False
        # QGIS 3.40 has geometryType(); QgsWkbTypes.isPolygon was added later.
        if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
            return True
        try:
            return QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PolygonGeometry
        except Exception:
            return False

    @staticmethod
    def _iter_layers_tree_order():
        """Layers in Layers-panel order, then any polygon layers not in the tree."""
        seen = set()
        root = QgsProject.instance().layerTreeRoot()

        def walk(node):
            for child in node.children():
                if isinstance(child, QgsLayerTreeLayer):
                    layer = child.layer()
                    if layer is not None:
                        seen.add(layer.id())
                        yield layer
                elif isinstance(child, QgsLayerTreeGroup):
                    yield from walk(child)

        yield from walk(root)
        for layer_id, layer in QgsProject.instance().mapLayers().items():
            if layer_id not in seen:
                yield layer

    def _populate_frame_layers(self):
        """Populate Frame Layer with every polygon layer; skip points and lines."""
        if not hasattr(self, 'combo_frame_layer'):
            return

        current_data = self.combo_frame_layer.currentData()
        self.combo_frame_layer.blockSignals(True)
        self.combo_frame_layer.clear()

        priority_layers = []
        regular_polygon_layers = []
        mask_layers = []

        active_layer = getattr(self.iface, 'activeLayer', lambda: None)()
        active_lid = active_layer.id() if active_layer else None

        site_keywords = ("fence", "factory", "n1", "n2", "boundary", "site", "prawet", "onnut", "park", "bkk")
        mask_keywords = ("invert", "mask", "dimmed")

        for layer in self._iter_layers_tree_order():
            if not self._is_polygon_layer(layer):
                continue
            name = layer.name()
            name_lower = name.lower()
            layer_id = layer.id()
            if any(kw in name_lower for kw in mask_keywords):
                mask_layers.append((name, layer_id))
            elif layer_id == active_lid or any(kw in name_lower for kw in site_keywords):
                priority_layers.append((name, layer_id))
            else:
                regular_polygon_layers.append((name, layer_id))

        for name, lid in priority_layers:
            self.combo_frame_layer.addItem(f"📐 {name}", lid)
        for name, lid in regular_polygon_layers:
            self.combo_frame_layer.addItem(f"📐 {name}", lid)
        for name, lid in mask_layers:
            self.combo_frame_layer.addItem(f"🔲 [Mask] {name}", lid)

        if self.combo_frame_layer.count() == 0:
            self.combo_frame_layer.addItem("No polygon layers found", "")
        else:
            best_idx = 0
            if current_data:
                idx = self.combo_frame_layer.findData(current_data)
                if idx >= 0:
                    best_idx = idx
            elif active_lid and self._is_polygon_layer(active_layer):
                idx = self.combo_frame_layer.findData(active_lid)
                if idx >= 0:
                    best_idx = idx
            elif priority_layers:
                idx = self.combo_frame_layer.findData(priority_layers[0][1])
                if idx >= 0:
                    best_idx = idx

            self.combo_frame_layer.setCurrentIndex(best_idx)

        self.combo_frame_layer.blockSignals(False)
        self.cached_frame_polygons = None
        self.cached_frame_shells = None

    def _fit_source_to_frame_layer(self):
        """Sets source mode to Selected Layer Extent targeting the framing layer and captures."""
        if not hasattr(self, 'combo_frame_layer'):
            return
        layer_id = self.combo_frame_layer.currentData()
        if not layer_id:
            return

        self.cached_frame_polygons = None
        self.cached_frame_shells = None
        idx = self.combo_layer.findData(layer_id)
        if idx >= 0:
            self.combo_source_type.setCurrentText("Selected Layer Extent")
            self.combo_layer.setCurrentIndex(idx)
            self.capture_source_image()
        else:
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer and hasattr(self.iface, 'mapCanvas'):
                canvas = self.iface.mapCanvas()
                ext = layer.extent()
                ext.scale(1.08)
                canvas.setExtent(ext)
                canvas.refresh()
                self.capture_source_image()

    def _extract_frame_layer_polygons(self):
        """
        Extract polygon rings from the framing layer in source-image coordinates.

        Returns (all_rings, exterior_shells) or (None, None). Geometries are
        reprojected to the captured map CRS, spatially filtered to the map
        extent, simplified to ~1 px, and cached.
        """
        if not hasattr(self, 'combo_frame_layer'):
            return None, None

        layer_id = self.combo_frame_layer.currentData()
        if not layer_id:
            return None, None

        selected_only = self.chk_frame_selected_only.isChecked() if hasattr(self, 'chk_frame_selected_only') else False

        if (self.cached_frame_polygons is not None and
            self.cached_frame_layer_id == layer_id and
            self.cached_frame_selected_only == selected_only and
            self.cached_render_extent == self.last_render_extent):
            return self.cached_frame_polygons, self.cached_frame_shells

        layer = QgsProject.instance().mapLayer(layer_id)
        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            return None, None

        if self.last_render_extent is None:
            return None, None

        extent = self.last_render_extent
        dest_crs = self.last_render_crs
        w = self.last_render_size.width()
        h = self.last_render_size.height()

        if extent.width() <= 0 or extent.height() <= 0 or w <= 0 or h <= 0:
            return None, None

        buffered_ext = QgsRectangle(extent)
        buffered_ext.scale(1.15)
        clip_box_geom = QgsGeometry.fromRect(buffered_ext)
        px_tol = extent.width() / float(w)

        transform = None
        request = QgsFeatureRequest()
        request.setSubsetOfAttributes([])
        try:
            layer_rect = QgsRectangle(buffered_ext)
            if layer.crs().isValid() and dest_crs and dest_crs.isValid() and layer.crs() != dest_crs:
                to_layer = QgsCoordinateTransform(dest_crs, layer.crs(), QgsProject.instance())
                layer_rect = to_layer.transformBoundingBox(buffered_ext)
                transform = QgsCoordinateTransform(layer.crs(), dest_crs, QgsProject.instance())
            request.setFilterRect(layer_rect)
        except Exception:
            transform = None

        if selected_only and layer.selectedFeatureCount() > 0:
            features = layer.selectedFeatures()
        else:
            features = layer.getFeatures(request)

        rings = []
        shells = []
        max_total_pts = 8000
        max_rings = 80
        current_pts = 0

        x_min = extent.xMinimum()
        y_max = extent.yMaximum()
        ext_w = extent.width()
        ext_h = extent.height()

        def to_rel(pt):
            px = ((pt.x() - x_min) / ext_w) * w
            py = ((y_max - pt.y()) / ext_h) * h
            return (px - w / 2.0, py - h / 2.0)

        for feat in features:
            if current_pts > max_total_pts or len(rings) >= max_rings:
                break
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue

            if transform:
                geom = QgsGeometry(geom)
                try:
                    geom.transform(transform)
                except Exception:
                    pass

            try:
                if not geom.intersects(clip_box_geom):
                    continue
                clipped_geom = geom.intersection(clip_box_geom)
                if clipped_geom and not clipped_geom.isEmpty():
                    geom = clipped_geom
            except Exception:
                pass

            try:
                geom = geom.simplify(px_tol * 1.5)
            except Exception:
                pass

            polys = []
            try:
                if geom.isMultipart():
                    polys = geom.asMultiPolygon()
                else:
                    polys = [geom.asPolygon()]
            except Exception:
                try:
                    polys = geom.asMultiPolygon()
                except Exception:
                    polys = []

            for poly in polys:
                if not poly:
                    continue
                for i, ring_pts in enumerate(poly):
                    if len(ring_pts) < 3:
                        continue
                    ring_rel_pts = []
                    for pt in ring_pts:
                        ring_rel_pts.append(to_rel(pt))
                        current_pts += 1
                        if current_pts > max_total_pts:
                            break
                    if len(ring_rel_pts) >= 3:
                        rings.append(ring_rel_pts)
                        if i == 0:
                            shells.append(ring_rel_pts)
                    if current_pts > max_total_pts or len(rings) >= max_rings:
                        break

        self.cached_frame_polygons = rings if rings else None
        self.cached_frame_shells = shells if shells else None
        self.cached_frame_layer_id = layer_id
        self.cached_frame_selected_only = selected_only
        self.cached_render_extent = self.last_render_extent

        return self.cached_frame_polygons, self.cached_frame_shells

    def reset_to_defaults(self):
        """Resets all projection, framing, and styling controls to default values."""
        # 1. Reset Projection Standard to Isometric (30°-30° / 57.74%)
        self._set_preset("isometric")

        # 2. Reset Orientation Angle to 45 deg
        self.slider_angle.setValue(45)
        self.lbl_angle_val.setText("45°")

        # 3. Reset Framing & Bounding Mode
        self.combo_mode.setCurrentIndex(0) # Full Plan / Tight Box
        if hasattr(self, 'widget_frame_layer'):
            self.widget_frame_layer.setVisible(False)
        if hasattr(self, 'chk_frame_selected_only'):
            self.chk_frame_selected_only.setChecked(False)
        self.chk_tight.setChecked(True)
        self.spin_pad.setValue(12)

        # 4. Reset Stroke Outline
        self.chk_stroke.setChecked(True)
        self.spin_stroke.setValue(4)
        self.params.stroke_color = "#2563eb"
        self.btn_stroke_col.setStyleSheet("background-color: #2563eb; border: 1px solid #64748b; border-radius: 3px;")
        self.chk_dashed.setChecked(True)

        # 5. Reset 3D Architectural Base Plate
        self.chk_extrusion.setChecked(False)
        self.spin_depth.setValue(24)
        self.params.extrusion_color = "#cbd5e1"
        self.btn_ext_col.setStyleSheet("background-color: #cbd5e1; border: 1px solid #64748b; border-radius: 3px;")

        # 6. Re-render transformed map
        self._update_render()

    def _on_source_type_changed(self, index):
        src_mode = self.combo_source_type.currentText()
        self.combo_bookmark.setVisible(src_mode == "Spatial Bookmark")
        self.combo_layer.setVisible(src_mode == "Selected Layer Extent")
        self.combo_layout.setVisible(src_mode == "QGIS Print Layout")
        self.capture_source_image()

    def _set_preset(self, preset_key: str):
        preset = PROJECTION_PRESETS.get(preset_key)
        if preset:
            self.btn_iso.setChecked(preset_key == "isometric")
            self.btn_dim.setChecked(preset_key == "dimetric")
            self.btn_mil.setChecked(preset_key == "military")

            ratio = preset["ratio"]
            self.params.aspect_ratio = ratio
            self.slider_ratio.blockSignals(True)
            self.slider_ratio.setValue(int(ratio * 100))
            self.lbl_ratio_val.setText(f"{int(ratio * 100)}%")
            self.slider_ratio.blockSignals(False)
            self._update_render()

    def _on_ratio_slider_changed(self, val):
        self.btn_iso.setChecked(False)
        self.btn_dim.setChecked(False)
        self.btn_mil.setChecked(False)
        self.params.aspect_ratio = val / 100.0
        self.lbl_ratio_val.setText(f"{val}%")
        self._update_render()

    def _on_angle_changed(self, val):
        self.params.angle_deg = float(val)
        self.lbl_angle_val.setText(f"{val}°")
        self._update_render()

    def _on_frame_layer_changed(self, *args):
        self.cached_frame_polygons = None
        self.cached_frame_shells = None
        self._update_render()

    def _on_mode_changed(self, idx):
        self.params.mode = self.combo_mode.currentData()
        is_layer_mask = (self.params.mode == "layer_mask")
        if hasattr(self, 'widget_frame_layer'):
            self.widget_frame_layer.setVisible(is_layer_mask)
        self.cached_frame_polygons = None
        self.cached_frame_shells = None
        self._update_render()

    def _pick_stroke_color(self):
        col = QColorDialog.getColor(QColor(self.params.stroke_color), self, "Choose Boundary Stroke Color")
        if col.isValid():
            self.params.stroke_color = col.name()
            self.btn_stroke_col.setStyleSheet(f"background-color: {self.params.stroke_color}; border: 1px solid #64748b; border-radius: 3px;")
            self._update_render()

    def _pick_extrusion_color(self):
        col = QColorDialog.getColor(QColor(self.params.extrusion_color), self, "Choose 3D Base Plate Color")
        if col.isValid():
            self.params.extrusion_color = col.name()
            self.btn_ext_col.setStyleSheet(f"background-color: {self.params.extrusion_color}; border: 1px solid #64748b; border-radius: 3px;")
            self._update_render()

    def _apply_map_settings_flags(self, map_settings):
        """Safely applies antialiasing and high-quality rendering flags across all QGIS 3.x versions."""
        flags = map_settings.flags()
        for flag_name in ("Antialiasing", "LosslessImageRendering", "UseAdvancedEffects"):
            val = getattr(QgsMapSettings, flag_name, None)
            if val is None and hasattr(QgsMapSettings, "Flag"):
                val = getattr(QgsMapSettings.Flag, flag_name, None)
            if val is not None:
                try:
                    flags |= val
                except Exception:
                    pass
        map_settings.setFlags(flags)

    def _clamp_wh(self, w, h, max_edge=MAX_CAPTURE_EDGE):
        w = max(10, int(w))
        h = max(10, int(h))
        m = max(w, h)
        if m > max_edge:
            s = max_edge / float(m)
            w = max(10, int(w * s))
            h = max(10, int(h * s))
        return w, h

    def _render_layers_to_image(self, layers, extent, crs, w, h, transparent, scale_mult):
        w, h = self._clamp_wh(w, h)
        map_settings = QgsMapSettings()
        map_settings.setLayers(layers)
        map_settings.setExtent(extent)
        map_settings.setOutputSize(QSize(w, h))
        map_settings.setOutputDpi(96 * scale_mult)
        map_settings.setDestinationCrs(crs)
        self._apply_map_settings_flags(map_settings)
        bg = QColor(0, 0, 0, 0) if transparent else QColor(255, 255, 255, 255)
        map_settings.setBackgroundColor(bg)

        img = QImage(QSize(w, h), QImage.Format_ARGB32_Premultiplied)
        if img.isNull():
            w, h = self._clamp_wh(w, h, max_edge=4096)
            img = QImage(QSize(w, h), QImage.Format_ARGB32_Premultiplied)
        img.fill(bg)

        painter = QPainter(img)
        try:
            job = QgsMapRendererCustomPainterJob(map_settings, painter)
            job.start()
            job.waitForFinished()
        finally:
            painter.end()
        return img, w, h

    def capture_source_image(self, *args):
        """Render the source QGIS map canvas, bookmark, layer, or print layout."""
        if self._capturing:
            return
        self._capturing = True
        self.cached_frame_polygons = None
        self.cached_frame_shells = None
        self._export_dirty = True
        src_mode = self.combo_source_type.currentText()
        scale_mult = self.combo_res.currentData() or 2
        transparent = self.chk_transparent.isChecked()
        self._output_scale = int(scale_mult)
        self.lbl_stats.setText("Capturing map…")
        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:
            canvas = self.iface.mapCanvas()
            layers = list(canvas.layers())
            canvas_crs = canvas.mapSettings().destinationCrs()

            if src_mode == "Active Map Canvas":
                extent = canvas.extent()
                w = int(canvas.width() * scale_mult)
                h = int(canvas.height() * scale_mult)
                img, w, h = self._render_layers_to_image(
                    layers, extent, canvas_crs, w, h, transparent, scale_mult
                )
                self.raw_source_image = img
                self.last_render_extent = QgsRectangle(extent)
                self.last_render_crs = canvas_crs
                self.last_render_size = QSize(w, h)

            elif src_mode == "Spatial Bookmark":
                bm_id = self.combo_bookmark.currentData()
                bm = self.bookmarks_map.get(bm_id)
                if not bm:
                    return

                bm_extent = bm.extent()
                if hasattr(bm_extent, 'crs') and bm_extent.crs().isValid():
                    bm_crs = bm_extent.crs()
                elif hasattr(bm, 'crs') and callable(getattr(bm, 'crs')):
                    bm_crs = bm.crs()
                else:
                    bm_crs = QgsCoordinateReferenceSystem()

                dest_crs = canvas_crs if canvas_crs.isValid() else bm_crs
                if bm_crs.isValid() and dest_crs.isValid() and bm_crs != dest_crs:
                    xform = QgsCoordinateTransform(bm_crs, dest_crs, QgsProject.instance())
                    render_extent = xform.transformBoundingBox(bm_extent)
                else:
                    render_extent = bm_extent

                aspect = render_extent.height() / render_extent.width() if render_extent.width() > 0 else 1.0
                w = int(canvas.width() * scale_mult)
                h = int(w * aspect)
                img, w, h = self._render_layers_to_image(
                    layers, render_extent, dest_crs, w, h, transparent, scale_mult
                )
                self.raw_source_image = img
                self.last_render_extent = QgsRectangle(render_extent)
                self.last_render_crs = dest_crs
                self.last_render_size = QSize(w, h)

            elif src_mode == "Selected Layer Extent":
                layer_id = self.combo_layer.currentData()
                layer = QgsProject.instance().mapLayer(layer_id)
                if not layer:
                    return

                dest_crs = canvas_crs if canvas_crs.isValid() else layer.crs()
                extent = QgsRectangle(layer.extent())
                if layer.crs().isValid() and dest_crs.isValid() and layer.crs() != dest_crs:
                    xform = QgsCoordinateTransform(layer.crs(), dest_crs, QgsProject.instance())
                    extent = QgsRectangle(xform.transformBoundingBox(extent))
                extent.scale(1.05)
                if layer not in layers:
                    layers.append(layer)

                aspect = extent.height() / extent.width() if extent.width() > 0 else 1.0
                w = int(1200 * scale_mult)
                h = int(w * aspect)
                img, w, h = self._render_layers_to_image(
                    layers, extent, dest_crs, w, h, transparent, scale_mult
                )
                self.raw_source_image = img
                self.last_render_extent = extent
                self.last_render_crs = dest_crs
                self.last_render_size = QSize(w, h)

            elif src_mode == "QGIS Print Layout":
                layout_name = self.combo_layout.currentText()
                layout = QgsProject.instance().layoutManager().layoutByName(layout_name)
                if not layout:
                    QMessageBox.warning(self, "Layout Error", f"Layout '{layout_name}' not found.")
                    return

                page = layout.pageCollection().page(0)
                if not page:
                    return

                target_dpi = float(96.0 * scale_mult)
                page_size_mm = page.pageSize()
                w_px, h_px = self._clamp_wh(
                    page_size_mm.width() * target_dpi / 25.4,
                    page_size_mm.height() * target_dpi / 25.4,
                )

                exporter = QgsLayoutExporter(layout)
                img = exporter.renderPageToImage(0, QSize(w_px, h_px), target_dpi)
                if img.isNull():
                    temp_png = os.path.join(tempfile.gettempdir(), "qgis_layout_temp_capture.png")
                    settings = QgsLayoutExporter.ImageExportSettings()
                    settings.dpi = target_dpi
                    exporter.exportToImage(temp_png, settings)
                    img = QImage(temp_png)

                self.raw_source_image = img
                self.last_render_extent = None
                self.last_render_crs = None
                self.last_render_size = QSize(img.width(), img.height())
                try:
                    for item in layout.items():
                        if isinstance(item, QgsLayoutItemMap):
                            self.last_render_extent = QgsRectangle(item.extent())
                            if hasattr(item, "crs"):
                                self.last_render_crs = item.crs()
                            break
                except Exception:
                    pass

            self._update_render(immediate=True)
        except Exception as e:
            QMessageBox.warning(self, "Capture Error", f"Failed to capture map: {str(e)}")
        finally:
            QApplication.restoreOverrideCursor()
            self._capturing = False

    def _sync_params_from_ui(self):
        """Read UI controls into AxoParams. Outline/padding/depth scale with capture DPI."""
        try:
            if hasattr(self, 'combo_mode') and self.combo_mode is not None:
                mode_val = self.combo_mode.currentData()
                if mode_val:
                    self.params.mode = mode_val
            style_scale = float(self._output_scale or 1)
            if hasattr(self, 'chk_tight') and self.chk_tight is not None:
                self.params.tight_crop = self.chk_tight.isChecked()
            if hasattr(self, 'spin_pad') and self.spin_pad is not None:
                self.params.padding = int(round(self.spin_pad.value() * style_scale))
            if hasattr(self, 'spin_stroke') and hasattr(self, 'chk_stroke'):
                raw_stroke = self.spin_stroke.value() if self.chk_stroke.isChecked() else 0
                self.params.stroke_width = int(round(raw_stroke * style_scale)) if raw_stroke else 0
            if hasattr(self, 'chk_dashed') and self.chk_dashed is not None:
                self.params.is_dashed = self.chk_dashed.isChecked()
            if hasattr(self, 'chk_extrusion') and self.chk_extrusion is not None:
                self.params.has_extrusion = self.chk_extrusion.isChecked()
            if hasattr(self, 'spin_depth') and self.spin_depth is not None:
                self.params.extrusion_depth = max(1, int(round(self.spin_depth.value() * style_scale)))
        except RuntimeError:
            return False

        if self.params.mode == "layer_mask":
            rings, shells = self._extract_frame_layer_polygons()
            self.params.frame_polygons = rings
            self.params.frame_shells = shells
        else:
            self.params.frame_polygons = None
            self.params.frame_shells = None
        return True

    def _update_render(self, immediate: bool = False):
        """Debounced live preview. Full-resolution export happens on copy/save."""
        self._export_dirty = True
        if self.raw_source_image.isNull():
            return
        if immediate:
            self._preview_timer.stop()
            self._run_preview()
        else:
            self._preview_timer.start()

    def _downscale_for_preview(self, img: QImage):
        w, h = img.width(), img.height()
        edge = max(w, h)
        if edge <= PREVIEW_MAX_EDGE:
            return img, 1.0
        scale = PREVIEW_MAX_EDGE / float(edge)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        return img.scaled(nw, nh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation), scale

    def _mode_label(self):
        mode_str = str(self.params.mode).upper()
        if self.params.mode == "layer_mask":
            layer_name = self.combo_frame_layer.currentText() if hasattr(self, 'combo_frame_layer') else "LAYER"
            mode_str = f"LAYER MASK ({layer_name})"
            if not self.params.frame_polygons:
                mode_str += " · no polygon in view, using full plan"
        return mode_str

    def _run_preview(self):
        if self.raw_source_image.isNull():
            return
        if not self._sync_params_from_ui():
            return

        src, pscale = self._downscale_for_preview(self.raw_source_image)
        params = scale_params(self.params, pscale) if pscale != 1.0 else self.params
        preview = transform_qimage(src, params)
        if preview is None or preview.isNull():
            return

        self.preview_label.set_transformed_pixmap(QPixmap.fromImage(preview))

        ew, eh = estimate_output_size(
            self.raw_source_image.width(),
            self.raw_source_image.height(),
            self.params,
        )
        ratio_pct = int(self.params.aspect_ratio * 100)
        self.lbl_stats.setText(
            f"Export: {ew} × {eh} px  |  Source: {self.raw_source_image.width()} × "
            f"{self.raw_source_image.height()}  |  Ratio: {ratio_pct}%  |  "
            f"Angle: {int(self.params.angle_deg)}°  |  Mode: {self._mode_label()}"
        )

    def _render_export_image(self) -> QImage:
        """Full-resolution transform used by copy / save / layout insert."""
        if self.raw_source_image.isNull():
            return QImage()
        if not self._sync_params_from_ui():
            return QImage()
        if not self._export_dirty and not self._export_image.isNull():
            return self._export_image

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._export_image = transform_qimage(self.raw_source_image, self.params)
            self.transformed_image = self._export_image
            self._export_dirty = False
        finally:
            QApplication.restoreOverrideCursor()
        return self._export_image

    def _restore_copy_button(self):
        try:
            self.btn_copy.setText("📋 Copy to Clipboard (Cmd/Ctrl+C)")
            self.btn_copy.setStyleSheet(COPY_BTN_STYLE)
        except RuntimeError:
            pass

    def _on_copy_to_clipboard(self):
        """Copy the full-resolution transformed image to the clipboard."""
        image = self._render_export_image()
        if image.isNull():
            return
        success = copy_image_to_clipboard(image)
        if success:
            QToolTip.showText(
                self.btn_copy.mapToGlobal(QPointF(0, -20).toPoint()),
                "✓ Copied full-res PNG. Paste with Cmd/Ctrl+V in Illustrator / Affinity / PPT.",
            )
            self.btn_copy.setText("✓ Copied to Clipboard!")
            self.btn_copy.setStyleSheet(COPY_BTN_DONE_STYLE)
            QTimer.singleShot(2200, self._restore_copy_button)
            self.lbl_stats.setText(
                f"Copied {image.width()} × {image.height()} px  |  "
                f"Ratio: {int(self.params.aspect_ratio * 100)}%  |  "
                f"Angle: {int(self.params.angle_deg)}°  |  Mode: {self._mode_label()}"
            )
        else:
            QMessageBox.warning(self, "Clipboard Error", "Could not copy image to clipboard.")

    def _on_save_png(self):
        """Save the full-resolution transformed image as a transparent PNG."""
        image = self._render_export_image()
        if image.isNull():
            return

        proj_path = QgsProject.instance().fileName()
        default_dir = os.path.dirname(proj_path) if proj_path else os.path.expanduser("~")
        thesis_fig_dir = os.path.normpath(os.path.join(default_dir, "..", "docs", "proposal", "figures"))
        if os.path.isdir(thesis_fig_dir):
            default_dir = thesis_fig_dir

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Axonometric PNG",
            os.path.join(default_dir, "axonometric_plan.png"),
            "PNG Images (*.png);;All Files (*.*)"
        )

        if file_path:
            if not file_path.lower().endswith(".png"):
                file_path += ".png"
            if image.save(file_path, "PNG"):
                QMessageBox.information(self, "Saved", f"Axonometric image saved successfully to:\n{file_path}")
            else:
                QMessageBox.warning(self, "Save Error", f"Could not write PNG:\n{file_path}")

    def _on_insert_into_layout(self):
        """Insert the full-resolution transformed image into a QGIS Print Layout."""
        image = self._render_export_image()
        if image.isNull():
            return

        layout_manager = QgsProject.instance().layoutManager()
        layouts = layout_manager.printLayouts()
        if not layouts:
            QMessageBox.warning(self, "No Layout Found", "Please create or open a Print Layout in QGIS first.")
            return

        target_layout = None
        selected_name = self.combo_layout.currentText() if hasattr(self, "combo_layout") else ""
        if selected_name:
            target_layout = layout_manager.layoutByName(selected_name)
        if target_layout is None:
            target_layout = layouts[0]

        temp_img_path = os.path.join(tempfile.gettempdir(), "qgis_temp_axo.png")
        if not image.save(temp_img_path, "PNG"):
            QMessageBox.warning(self, "Insert Error", "Could not write a temporary PNG for the layout.")
            return

        pic_item = QgsLayoutItemPicture(target_layout)
        pic_item.setPicturePath(temp_img_path)
        pic_item.attemptMove(QgsLayoutPoint(20, 20, QgsUnitTypes.LayoutMillimeters))
        aspect = image.height() / float(max(1, image.width()))
        pic_item.attemptResize(QgsLayoutSize(120, 120 * aspect, QgsUnitTypes.LayoutMillimeters))
        target_layout.addItem(pic_item)

        QMessageBox.information(
            self,
            "Inserted into Layout",
            f"Inserted axonometric plate into layout '{target_layout.name()}'.",
        )
