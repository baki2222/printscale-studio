"""
Brand assets (PrintScaleStudio_Brand_Kit): application icon and the theme-matched logo.
The files live in printscale/assets/brand; in the frozen app PyInstaller places the same tree under
sys._MEIPASS, so one relative path works from source, the portable ZIP and the installed app.
"""

import os
import sys

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap

ICON_ICO = "PrintScaleStudio_Windows.ico"
ICON_SVG = "PrintScaleStudio_Icon.svg"
LOGO_DARK_INK = "PrintScaleStudio_Logo.svg"         # dark lettering, for light surfaces
LOGO_LIGHT_INK = "PrintScaleStudio_Logo_Light.svg"  # light lettering, for dark surfaces


def brand_dir() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "printscale", "assets", "brand")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "brand")


def asset_path(name: str) -> str:
    return os.path.join(brand_dir(), name)


def app_icon() -> QIcon:
    """Multi-resolution Windows icon (16-256 px) with the SVG master as a scalable fallback."""
    icon = QIcon(asset_path(ICON_ICO))
    if icon.isNull() or not icon.availableSizes():
        icon = QIcon(asset_path(ICON_SVG))
    return icon


def logo_for_theme(theme_name: str) -> str:
    """Dark theme -> light lettering; light theme -> dark lettering."""
    return LOGO_LIGHT_INK if theme_name == "dark" else LOGO_DARK_INK


def render_logo(theme_name: str, height: int, device_pixel_ratio: float = 1.0) -> QPixmap:
    """Renders the transparent vector logo at `height` logical px, sharp at the given scale."""
    from PySide6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(asset_path(logo_for_theme(theme_name)))
    if not renderer.isValid():
        return QPixmap()
    vb = renderer.viewBoxF()
    width = round(height * vb.width() / vb.height())
    img = QImage(QSize(round(width * device_pixel_ratio), round(height * device_pixel_ratio)),
                 QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, img.width(), img.height()))
    painter.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(device_pixel_ratio)
    return pm
