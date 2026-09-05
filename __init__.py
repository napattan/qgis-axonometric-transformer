# -*- coding: utf-8 -*-
"""
Axonometric Map Transformer - QGIS Plugin Initialization Factory
"""

def classFactory(iface):
    """QGIS plugin factory function.
    
    Args:
        iface: QgisInterface instance passed by QGIS runtime.
        
    Returns:
        AxonometricTransformerPlugin instance.
    """
    from .plugin import AxonometricTransformerPlugin
    return AxonometricTransformerPlugin(iface)
