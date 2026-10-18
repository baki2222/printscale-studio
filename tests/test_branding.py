"""
Brand kit integration: exact asset copies, a usable multi-size window icon, and the About logo
variant that contrasts with each theme. Runs on the offscreen Qt platform with an isolated APPDATA.
"""

import hashlib
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from printscale.ui import branding  # noqa: E402

# SHA-256 values from PrintScaleStudio_Brand_Kit/ASSET_MANIFEST.json
KIT = {
    "PrintScaleStudio_Icon.svg": "771bb8dec29b20586664628358b298535fc50a44d207750efd78af1dc173536e",
    "PrintScaleStudio_Logo.svg": "c87aec44a096557c5885a8f591e775929c68dac407bddd5eefc229b91d602b0f",
    "PrintScaleStudio_Logo_Light.svg": "e0af658d4e916961a77c33baa2a17b5904e37d733ca4a49c275836f366eb9546",
    "PrintScaleStudio_Windows.ico": "8c418227b42da74266108d04006a7a35bc0c41ccc32ab70bf2b40d90573c8add",
    "FONT_LICENSE.txt": "63d3ba759d12804c5b31a9d5940d855c1820d1f5999e6b0872eb1c7ff045fbc9",
}


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_brand_assets_are_exact_kit_copies():
    for name, digest in KIT.items():
        with open(branding.asset_path(name), "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest() == digest, name


def test_app_icon_has_all_windows_sizes(qapp):
    icon = branding.app_icon()
    sizes = {s.width() for s in icon.availableSizes()}
    assert {16, 20, 24, 32, 40, 48, 64, 96, 128, 256} <= sizes
    assert not icon.pixmap(QSize(32, 32)).isNull()


def test_frozen_path_resolves_under_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(branding.sys, "frozen", True, raising=False)
    monkeypatch.setattr(branding.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert branding.brand_dir() == os.path.join(str(tmp_path), "printscale", "assets", "brand")


def _ink_luminance(pm):
    """Mean luminance of the opaque lettering area (right part of the logo, past the icon mark)."""
    img = pm.toImage().convertToFormat(pm.toImage().Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine() // 4, 4)[:, :w]
    text = arr[:, int(w * 0.32):]
    opaque = text[..., 3] > 200
    assert opaque.sum() > 100
    rgb = text[opaque][:, :3].astype(float)
    assert (arr[0, 0, 3] == 0) and (arr[-1, -1, 3] == 0), "logo background must stay transparent"
    return float((0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2]).mean())


def test_logo_variant_matches_theme(qapp):
    assert branding.logo_for_theme("dark") == branding.LOGO_LIGHT_INK
    assert branding.logo_for_theme("light") == branding.LOGO_DARK_INK
    dark_pm = branding.render_logo("dark", 44, 1.5)
    light_pm = branding.render_logo("light", 44, 1.5)
    assert dark_pm.devicePixelRatio() == 1.5 and dark_pm.height() == 66
    assert _ink_luminance(dark_pm) > 200   # #F5F7FE lettering on dark surfaces
    assert _ink_luminance(light_pm) < 60   # #17213B lettering on light surfaces


def test_window_and_about_dialog_use_brand(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from printscale.ui import main_window as mw
    win = mw.MainWindow()
    try:
        assert not win.windowIcon().isNull()
        assert {s.width() for s in win.windowIcon().availableSizes()} >= {16, 32, 256}
        for theme in ("dark", "light"):
            win._apply_theme(theme, save=False)
            box = win._build_about_dialog()
            assert isinstance(box, QMessageBox)
            pm = box.iconPixmap()
            assert not pm.isNull() and pm.width() > pm.height() * 3  # the wide wordmark logo
            lum = _ink_luminance(pm)
            assert (lum > 200) if theme == "dark" else (lum < 60)
            box.deleteLater()
    finally:
        win.is_auto_test = True
        win.close()
        win.deleteLater()
