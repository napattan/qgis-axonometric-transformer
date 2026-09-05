# 📐 Axonometric Map Transformer — QGIS Plugin

[![QGIS](https://img.shields.io/badge/QGIS-3.16+-brightgreen.svg)](https://qgis.org)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://python.org)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

> **Direct QGIS to 3D Axonometric & Isometric Plan Generator**  
> Eliminates the manual *"Export 2D Map → Switch to Graphic Software → Skew/Rotate/Extrude"* pipeline. Transform the active QGIS map canvas, selected layer extents, or print layouts into presentation-ready 3D axonometric diagram plates with **1-click clipboard copy (`Ctrl+C` / `Cmd+C`)** directly into Adobe Illustrator, Affinity Designer, Photoshop, and slide presentations.

---

## 🌟 Key Features

### 1. Direct In-QGIS Capture
- **Active Map Canvas**: Instant capture of whatever is currently on screen in QGIS.
- **Selected Layer Extent**: Automatically zooms, centers, and renders the active vector layer (e.g., site boundary, masterplan fence, subzone polygon) with custom padding.
- **QGIS Print Layout**: Renders any pre-composed QGIS Print Layout at high resolution.
- **Resolution Multipliers**: Screen Res (1×), High-DPI (150 DPI / 2×), and Print Ready (300 DPI / 4×).
- **Transparent Alpha Channel**: Renders only map vectors, labels, and geometry with transparent background for seamless diagram stacking.

### 2. Standard Mathematical Projections
- **Isometric (30°-30°)**: True ground plane vertical compression (H = W / √3 ≈ 57.735%).
- **Dimetric (2:1)**: 50.00% height ratio for high-elevation architectural legibility.
- **Military / Oblique (45° Axo)**: 70.71% height ratio preserving true horizontal angles.
- **Custom Ratio**: Continuous slider from 20% to 100%.
- **Plan Rotation**: Continuous rotation from -180° to +180° with preset chips (`-45°`, `0° North`, `+45°`, `+90°`).

### 3. Framing Modes & 3D Architectural Base Plates
- **Full Plan / Tight Bounding Box**: Tight bounding crop around rotated map extent.
- **Circular Site Disc**: Full-bleed circular site pedestal.
- **Isometric Diamond**: Architectural diamond plan framing.
- **Vector Boundary Masking**: Directly clips the axonometric map to any chosen polygon layer (eliminating the need to create inverted mask layers manually).
- **3D Base Plate Extrusion**: Adds bottom slab extrusion depth and realistic facet shading to generate floating 3D architectural site pedestals.

### 4. 1-Click Clipboard & Export
- **Copy to Clipboard (`Ctrl+C` / `Cmd+C`)**: Copies full-resolution 32-bit PNG with alpha directly to OS clipboard. Paste with `Ctrl+V` into Illustrator, Affinity, Photoshop, or PowerPoint.
- **Save High-Res PNG**: Saves directly to disk with transparent alpha channel.
- **Insert into QGIS Print Layout**: Adds the transformed plate as a picture item directly into your open print layout.

---

## 🚀 Installation

### Method A: From QGIS Official Plugin Repository (Recommended)
1. Open **QGIS Desktop**.
2. Go to top menu: **Plugins > Manage and Install Plugins...**
3. Search for **Axonometric Map Transformer**.
4. Click **Install Plugin**.

### Method B: Manual Installation via Script
Clone or download this repository, then run:
```bash
python install_plugin.py
```
*(Automatically links or copies files into your QGIS default profile plugin directory).*

---

## 📋 File Architecture

```text
axonometric_transformer/
├── metadata.txt              # QGIS plugin metadata & versioning
├── __init__.py               # Plugin initialization factory
├── plugin.py                 # QGIS menu and toolbar action hooks
├── transformer_core.py       # Affine geometry, squashing, & extrusion engine
├── transformer_dialog.py     # PyQt5 UI dialog & interactive preview
├── icon.png                  # Plugin toolbar icon (PNG)
├── icon.svg                  # Vector icon (SVG)
└── README.md                 # Documentation
```

---

## 📜 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)** — see the [LICENSE](LICENSE) file for details.

## 👤 Author

**Napat Phasundhiae**  
*Computational Design Technologist*  
- GitHub: [@napattan](https://github.com/napattan)
- Repository: [qgis-axonometric-transformer](https://github.com/napattan/qgis-axonometric-transformer)
