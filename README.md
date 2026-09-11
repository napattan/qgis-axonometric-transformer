# 📐 Axonometric Map Transformer - QGIS Plugin

[![Version](https://img.shields.io/badge/Version-v1.2.0-blue.svg)](https://github.com/napattan/qgis-axonometric-transformer)
[![Portal](https://img.shields.io/badge/plugins.qgis.org-Approved%20%236219-brightgreen.svg)](https://plugins.qgis.org/plugins/axonometric_transformer/)
[![Plugin Manager](https://img.shields.io/badge/Plugin%20Manager-v1.1.3%20Live%20%2F%20v1.2.0%20Pending-blue.svg)](https://plugins.qgis.org/plugins/axonometric_transformer/)
[![QGIS 4 Ready](https://img.shields.io/badge/QGIS%204%20Ready-Local%20AST%20verified-brightgreen.svg)](https://github.com/napattan/qgis-axonometric-transformer)
[![QGIS](https://img.shields.io/badge/QGIS-3.16%2B%20%2F%204.x-brightgreen.svg)](https://qgis.org)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://python.org)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

> **Direct QGIS to 3D Axonometric & Isometric Plan Generator**  
> Eliminates the manual *"Export 2D Map → Switch to Graphic Software → Skew/Rotate/Extrude"* pipeline. Transform the active QGIS map canvas, selected layer extents, or print layouts into presentation-ready 3D axonometric diagram plates with **1-click clipboard copy (`Ctrl+C` / `Cmd+C`)** directly into Adobe Illustrator, Affinity Designer, Photoshop, and slide presentations.

**Release status (truth lock):** Approved on [plugins.qgis.org](https://plugins.qgis.org/plugins/axonometric_transformer/) as Plugin ID **6219** (`axonometric_transformer`). **v1.1.3** is LIVE with 1-click in-app install via **Plugins → Manage and Install Plugins**. **v1.2.0** (Framing fill ground, solid 3D extrusion, 5% opacity snapping) is tagged on GitHub and uploaded to the portal, currently pending official repository validation. Portal security scan: 100% pass, 0 issues. QGIS 4 Ready.

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
- **Framing Fill Ground**: Fill the interior of the framing boundary with customizable solid or translucent ground colors and independent opacity control.
- **Solid 3D Base Plate Extrusion**: Adds bottom slab extrusion depth and realistic facet shading. Features continuous front-wall extrusion with dynamic winding order calculation, Painter's algorithm depth sorting, and solid top cap under transparent maps.
- **Base Plate Opacity with 5% Step Snapping**: Independent opacity slider with 5% notch snapping for both Framing Fill and 3D Base Plate.

### 4. 1-Click Clipboard & Export
- **Copy to Clipboard (`Ctrl+C` / `Cmd+C`)**: Copies full-resolution 32-bit PNG with alpha directly to OS clipboard. Paste with `Ctrl+V` into Illustrator, Affinity, Photoshop, or PowerPoint.
- **Save High-Res PNG**: Saves directly to disk with transparent alpha channel.
- **Insert into QGIS Print Layout**: Adds the transformed plate as a picture item directly into your open print layout.

---

## 🚀 Installation
 
### Method A: Official QGIS Plugin Manager (Recommended)
Now available directly in the official QGIS repository:
1. Open **QGIS Desktop** (3.16+).
2. Navigate to **Plugins → Manage and Install Plugins...**
3. Select the **All** tab and search for **`Axonometric Map Transformer`**.
4. Click **Install Plugin** (installs active release v1.1.3; v1.2.0 updates automatically once portal validation clears).
 
*(The leaf/cube icon will appear immediately in your Toolbar and under the **Plugins → Axonometric Map Transformer** menu).*

### Method B: Manual Installation (For Developers)
Clone or download this repository, then run:
```bash
python install_plugin.py
```
*(Automatically symlinks or copies files into your QGIS default profile plugin directory.)* Then enable the plugin under **Plugins → Manage and Install Plugins → Installed**.

---

## 📋 File Architecture

```text
axonometric_transformer/
├── metadata.txt              # QGIS plugin metadata & versioning
├── __init__.py               # Plugin initialization factory
├── plugin.py                 # QGIS menu and toolbar action hooks
├── transformer_core.py       # Affine geometry, squashing, & extrusion engine
├── transformer_dialog.py     # PyQt5 / PyQt6 (qgis.PyQt) UI dialog & interactive preview
├── icon.png                  # Plugin toolbar icon (PNG)
├── icon.svg                  # Vector icon (SVG)
└── README.md                 # Documentation
```

---

## 📜 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)** - see the [LICENSE](LICENSE) file for details.

## 👤 Author

**Napat Phasundhiae**  
*Computational Design Technologist | Spatial Analytics • Urban & Environmental Simulation • Workflow Automation*  
- GitHub: [@napattan](https://github.com/napattan)
- LinkedIn: [linkedin.com/in/napatphas](https://www.linkedin.com/in/napatphas/)
- Repository: [qgis-axonometric-transformer](https://github.com/napattan/qgis-axonometric-transformer)
- Portal listing: [plugins.qgis.org/plugins/axonometric_transformer](https://plugins.qgis.org/plugins/axonometric_transformer/) (ID 6219; v1.1.3 live in manager, v1.2.0 pending validation)
