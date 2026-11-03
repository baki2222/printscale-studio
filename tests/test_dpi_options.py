"""
DPI choices: the 800 and 1000 presets and the Custom DPI field. Covers selection behaviour, the pixel sizes
they produce, persistence across restarts, the over-limit warning, and the resolution written to saved files
(checked by parsing the PNG/JPEG bytes, not with the app's own reader).
"""
import json
import os
import struct
import time

import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from printscale.core.enhancement import ProcessingMode  # noqa: E402
from printscale.core.geometry import DimensionMode  # noqa: E402
from printscale.core.pipeline import JobParameters, execute_pipeline  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """Isolated APPDATA; returns the path of the settings file the app writes."""
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    for n in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: None))
    return appdata / "PrintScaleStudio" / "config.json"


def pump(qapp, seconds=0.05):
    end = time.time() + seconds
    while time.time() < end:
        qapp.processEvents()


def open_window():
    from printscale.ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    return w


def close(w, qapp):
    w.close()
    pump(qapp, 0.1)
    w.deleteLater()


def checked_dpi_buttons(cv):
    return [b.text() for b in cv.dpi_group.buttons() if b.isChecked()]


def use_print_size(cv, w_in, h_in):
    cv.rb_dim_print.setChecked(True)
    cv.chk_lock_aspect.setChecked(False)
    cv.combo_unit.setCurrentText("in")
    cv.spin_print_w.setValue(w_in)
    cv.spin_print_h.setValue(h_in)


def test_dpi_buttons_include_800_1000_and_custom(qapp, profile):
    w = open_window()
    try:
        cv = w.controls_view
        assert [b.text() for b in cv.dpi_group.buttons()] == ["300", "400", "500", "600", "800", "1000", "Custom"]
        assert checked_dpi_buttons(cv) == ["300"]
        assert not cv.custom_dpi_widget.isVisibleTo(cv)
    finally:
        close(w, qapp)


@pytest.mark.parametrize("dpi, pixels", [(800, (11200, 12800)), (1000, (14000, 16000))])
def test_high_dpi_presets_size_a_14x16_inch_print(qapp, profile, dpi, pixels):
    w = open_window()
    try:
        cv = w.controls_view
        use_print_size(cv, 14.0, 16.0)
        getattr(cv, f"btn_dpi_{dpi}").click()
        assert cv.get_dpi() == dpi and checked_dpi_buttons(cv) == [str(dpi)]
        assert cv.get_target_dimensions() == pixels
        assert f"at {dpi} DPI" in cv.lbl_phys_info.text()
        assert not cv.custom_dpi_widget.isVisibleTo(cv)
    finally:
        close(w, qapp)


def test_custom_dpi_field(qapp, profile):
    w = open_window()
    try:
        cv = w.controls_view
        use_print_size(cv, 14.0, 16.0)
        cv.btn_dpi_custom.click()
        assert cv.custom_dpi_widget.isVisibleTo(cv) and checked_dpi_buttons(cv) == ["Custom"]
        assert cv.spin_custom_dpi.minimum() == 72 and cv.spin_custom_dpi.maximum() == 1200

        cv.spin_custom_dpi.setValue(720)
        assert cv.get_dpi() == 720 and cv.get_target_dimensions() == (10080, 11520)
        assert "at 720 DPI" in cv.lbl_phys_info.text()

        # Typing a value that happens to be a preset keeps Custom selected (no jumping while typing)
        cv.spin_custom_dpi.setValue(800)
        assert checked_dpi_buttons(cv) == ["Custom"] and cv.custom_dpi_widget.isVisibleTo(cv)

        # Choosing a preset leaves custom mode and hides the field
        cv.btn_dpi_400.click()
        assert cv.get_dpi() == 400 and checked_dpi_buttons(cv) == ["400"]
        assert not cv.custom_dpi_widget.isVisibleTo(cv)

        # The size presets reset to 300 DPI
        cv.btn_dpi_custom.click()
        cv.spin_custom_dpi.setValue(950)
        cv.btn_preset_apparel.click()
        assert cv.get_dpi() == 300 and checked_dpi_buttons(cv) == ["300"]
        assert not cv.custom_dpi_widget.isVisibleTo(cv)
    finally:
        close(w, qapp)


@pytest.mark.parametrize("dpi, expect_custom", [(720, True), (1000, False)])
def test_dpi_choice_survives_restart(qapp, profile, dpi, expect_custom):
    w = open_window()
    cv = w.controls_view
    if expect_custom:
        cv.btn_dpi_custom.click()
        cv.spin_custom_dpi.setValue(dpi)
    else:
        getattr(cv, f"btn_dpi_{dpi}").click()
    close(w, qapp)
    assert json.loads(profile.read_text(encoding="utf-8"))["default_dpi"] == dpi

    w2 = open_window()
    try:
        cv2 = w2.controls_view
        assert cv2.get_dpi() == dpi
        assert checked_dpi_buttons(cv2) == (["Custom"] if expect_custom else [str(dpi)])
        assert cv2.custom_dpi_widget.isVisibleTo(cv2) == expect_custom
    finally:
        close(w2, qapp)


def test_summary_warns_before_the_canvas_limit(qapp, profile):
    w = open_window()
    try:
        cv = w.controls_view
        use_print_size(cv, 30.0, 30.0)
        cv.btn_dpi_custom.click()
        cv.spin_custom_dpi.setValue(1200)  # 36,000 px per side
        assert cv.get_target_dimensions() == (36000, 36000)
        assert "30,000" in cv.lbl_upload_preset.text() and cv.lbl_upload_preset.objectName() == "error"
        cv.btn_dpi_800.click()  # 24,000 px: exportable, but over the upload profile
        assert "23,000" in cv.lbl_upload_preset.text()
    finally:
        close(w, qapp)


def png_phys(path):
    data = open(path, "rb").read()
    i, found = 8, []
    while i < len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        if data[i + 4:i + 8] == b"pHYs":
            found.append(struct.unpack(">IIB", data[i + 8:i + 17]))
        i += 12 + n
    return found


def jfif_density(path):
    data = open(path, "rb").read()
    j = data.index(b"JFIF\x00")
    return struct.unpack(">BHH", data[j + 7:j + 12])


@pytest.mark.parametrize("dpi", [800, 1000, 720])
@pytest.mark.parametrize("fmt", ["PNG", "JPEG"])
def test_saved_files_carry_the_chosen_dpi(tmp_path, dpi, fmt):
    src = tmp_path / "art.png"
    rgba = np.zeros((90, 120, 4), np.uint8)
    rgba[10:80, 15:105] = (40, 160, 220, 255)
    Image.fromarray(rgba, "RGBA").save(src)
    out = tmp_path / ("out.png" if fmt == "PNG" else "out.jpg")
    res = execute_pipeline(JobParameters(
        source_path=str(src), output_path=str(out), output_format=fmt, dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=240, pixel_height=180, dpi=dpi, processing_mode=ProcessingMode.PRESERVE_ARTWORK))
    assert res.success, res.error_message
    assert abs(res.output_dpi - dpi) < 0.05
    if fmt == "PNG":
        assert png_phys(out) == [(round(dpi / 0.0254), round(dpi / 0.0254), 1)]
    else:
        assert jfif_density(out) == (1, dpi, dpi)
        exif = Image.open(out).getexif()
        assert float(exif[0x011A]) == dpi and float(exif[0x011B]) == dpi and exif[0x0128] == 2
