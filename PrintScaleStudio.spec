# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PrintScale Studio (Windows x64, one-folder build).
# Build with: python scripts/build_package.py   (it fetches/verifies models and checks the result)
import os

ROOT = os.path.abspath(SPECPATH)
BRAND = os.path.join(ROOT, "printscale", "assets", "brand")
MODELS = [os.path.join(ROOT, "models", f) for f in ("RealESRGAN_x4plus_anime_6B.onnx", "RealESRGAN_x4plus.onnx")]

# The app uses only QtCore, QtGui, QtWidgets and QtSvg. The PySide6 hooks also collect Qt Virtual
# Keyboard (GPLv3-only for open-source use), Qt Quick/QML, Qt PDF, Qt Network/TLS and the software
# OpenGL renderer. None of them is used, so they are left out of the package; build_package.py
# verifies that none of these files is present.
QT_EXCLUDE = (
    "qt6virtualkeyboard", "qtvirtualkeyboardplugin", "platforminputcontexts",
    "qt6quick", "qt6qml", "pyside6/qml/", "qt6pdf", "imageformats/qpdf",
    "qt6network", "qtnetwork.pyd", "plugins/tls", "plugins/networkinformation",
    "qt6opengl", "opengl32sw",
)


def keep(entry):
    dest = entry[0].replace("\\", "/").lower()
    return not any(p in dest for p in QT_EXCLUDE)


a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(m, "models") for m in MODELS] + [(BRAND, "printscale/assets/brand")],
    hiddenimports=["PIL._imagingcms", "PIL.ImageCms", "onnxruntime", "PySide6.QtCore", "PySide6.QtGui",
                   "PySide6.QtWidgets", "PySide6.QtSvg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "torchvision", "onnx", "sympy", "networkx", "jinja2", "fsspec", "pytest",
              "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtOpenGL", "PySide6.QtPdf"],
    noarchive=False,
    optimize=0,
)
a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PrintScaleStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(BRAND, "PrintScaleStudio_Windows.ico")],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PrintScaleStudio",
)
