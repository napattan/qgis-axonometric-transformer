# -*- coding: utf-8 -*-
"""
Axonometric Map Transformer - QGIS Plugin Main Lifecycle
Registers toolbar actions, menu items, and handles dialog lifecycle.
"""

import os
from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .transformer_dialog import AxonometricTransformerDialog


class AxonometricTransformerPlugin:
    """Main QGIS Plugin class for Axonometric Map Transformer."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.dialog = None
        self.action = None
        self.menu_name = "&Axonometric Map Transformer"

    def initGui(self):
        """Creates the GUI elements (Menu item, toolbar button)."""
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(icon, "Axonometric Map Transformer", self.iface.mainWindow())
        self.action.setStatusTip("Transform active QGIS canvas/layout into 3D isometric & axonometric diagram with 1-click clipboard copy")
        self.action.triggered.connect(self.run)

        # Add to Plugins Menu & Toolbar
        self.iface.addPluginToMenu(self.menu_name, self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        if self.action:
            self.iface.removePluginMenu(self.menu_name, self.action)
            self.iface.removeToolBarIcon(self.action)
            del self.action

        if self.dialog:
            self.dialog.close()
            self.dialog = None

    def run(self):
        """Launches the interactive Axonometric Transformer dialog."""
        if self.dialog is not None:
            try:
                # Check if underlying C++ object is alive
                self.dialog.isVisible()
            except (RuntimeError, Exception):
                self.dialog = None

        if self.dialog is None:
            self.dialog = AxonometricTransformerDialog(self.iface, self.iface.mainWindow())
        else:
            try:
                self.dialog.refresh_project_lists()
            except Exception:
                self.dialog = AxonometricTransformerDialog(self.iface, self.iface.mainWindow())

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

