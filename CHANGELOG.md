# Changelog

## [1.2.1]

- In-Memory Multi-Format Clipboard Engine: Direct embedded paste with transparent background into Adobe Illustrator and Affinity Designer via in-memory PDF with soft mask alpha (`/SMask`).
- Added `image/svg+xml` clipboard format for Figma and `image/png` for Canva, Photoshop, and Microsoft Office.
- Zero temporary disk files during clipboard copy (100% in-memory transit).
- Fixed Qt6 AST forward-compatibility: explicitly scoped `QPageSize.Unit.Point` and `QPageLayout.Orientation.Portrait` for the in-memory PDF writer, earning the official green **QGIS 4 Ready** badge.
- 100% Flake8 / PEP8 code quality compliance (0 violations across entire codebase).
- Upgraded pre-flight security gates and privacy protections.

## [1.2.0]

- Added Framing Fill ground option with customizable color and opacity.
- Added 3D Base Plate opacity slider with 5 percent step snapping.
- Solid 3D Base Plate engine: continuous front-wall extrusion with dynamic winding order detection, Painter's algorithm depth sorting, and solid top cap under transparent maps.
- Clean aligned Section 3 UI grid layout with dual sliders.
- Verified 100 percent Qt6 / QGIS 4 forward-compatibility.

## [1.1.3]

- Approved and published on official QGIS plugin repository (Plugin ID: 6219).
- Passed portal security scan (0 issues) and Qt6 / QGIS 4 forward-compatibility.
- Fixed root package naming slug for seamless in-app Plugin Manager installation.
- 1-click in-app install live via QGIS Plugin Manager.
