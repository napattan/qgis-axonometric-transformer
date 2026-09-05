# -*- coding: utf-8 -*-
"""
Installer Script for QGIS Axonometric Transformer Plugin.
Copies or creates a directory link into QGIS default profile plugins directory.
"""

import os
import sys
import shutil

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def get_plugins_dir():
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("APPDATA environment variable not found.")
        return os.path.join(appdata, "QGIS", "QGIS3", "profiles", "default", "python", "plugins")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins")
    else:
        return os.path.expanduser("~/.local/share/QGIS/QGIS3/profiles/default/python/plugins")


def install():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugins_dir = get_plugins_dir()
    if not os.path.exists(plugins_dir):
        print(f"Creating plugins directory: {plugins_dir}")
        os.makedirs(plugins_dir, exist_ok=True)

    target_plugin_dir = os.path.join(plugins_dir, "axonometric_transformer")
    print(f"Installing plugin to: {target_plugin_dir}")

    files_to_copy = [
        "__init__.py",
        "metadata.txt",
        "plugin.py",
        "transformer_core.py",
        "transformer_dialog.py",
        "icon.png",
        "icon.svg"
    ]

    if os.path.islink(target_plugin_dir) or os.path.isdir(target_plugin_dir):
        if os.path.islink(target_plugin_dir):
            os.remove(target_plugin_dir)
        else:
            shutil.rmtree(target_plugin_dir)

    # Live-link on macOS/Linux so QGIS picks up source edits after a plugin reload.
    if sys.platform != "win32":
        os.symlink(script_dir, target_plugin_dir)
        print(f"  ✓ Linked {script_dir}")
        print(f"    → {target_plugin_dir}")
    else:
        os.makedirs(target_plugin_dir, exist_ok=True)
        for fname in files_to_copy:
            src = os.path.join(script_dir, fname)
            dst = os.path.join(target_plugin_dir, fname)
            if os.path.exists(src):
                shutil.copy2(src, dst)
                print(f"  ✓ Copied {fname}")
            else:
                print(f"  ⚠ Warning: {fname} not found in source directory.")

    print("\n✅ Axonometric Map Transformer plugin successfully installed!")
    print("Next steps:")
    print("1. Open QGIS (or restart QGIS if already open).")
    print("2. Go to 'Plugins > Manage and Install Plugins... > Installed'.")
    print("3. Check 'Axonometric Map Transformer' to enable it.")
    print("4. Click the 3D isometric cube icon on the toolbar or access via 'Plugins > Axonometric Map Transformer'.")

if __name__ == "__main__":
    install()
