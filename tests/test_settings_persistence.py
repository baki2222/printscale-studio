"""
U-5: saved preferences must be shown after restart, must drive the actual JobParameters and
exports, must not be overwritten by start-up signals, and must survive invalid values.
U-6: the crop preview must use surrounding context and match the corresponding export region.
Every test runs real MainWindow instances in an isolated %APPDATA% profile.
"""

import io
import json
import os
import time
import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from printscale.core.geometry import DimensionMode  # noqa: E402
from printscale.core.enhancement import ProcessingMode  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def profile(tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    for n in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: None))
    from printscale.ui import main_window as mw
    monkeypatch.setattr(mw.SummaryDialog, "exec", lambda self: 0)
    monkeypatch.setattr(mw.BatchSummaryDialog, "exec", lambda self: 0)
    return appdata / "PrintScaleStudio" / "config.json"


def pump(qapp, seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


def wait_until(qapp, pred, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    return False


def new_window():
    from printscale.ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    return w


def close(w, qapp):
    w.close()
    pump(qapp, 0.1)
    w.deleteLater()


def test_non_default_preferences_survive_restart_and_drive_exports(qapp, profile, tmp_path, monkeypatch):
    w = new_window()
    cv = w.controls_view
    cv.rb_illustration.setChecked(True)
    cv.rb_jpg.setChecked(True)
    cv.btn_dpi_500.click()
    cv.slider_sharpen.setValue(35)
    cv.slider_jpeg_q.setValue(82)
    cv.combo_composition.setCurrentIndex(1)  # crop
    cv.chk_lock_aspect.setChecked(False)
    cv.rb_dim_pixel.setChecked(True)
    cv.spin_px_w.setValue(160)
    cv.spin_px_h.setValue(120)
    cv._current_bg_color = (10, 20, 30)
    cv._trigger_update()
    close(w, qapp)

    saved = json.loads(profile.read_text(encoding="utf-8"))
    assert saved["default_dpi"] == 500 and saved["default_format"] == "JPEG"
    assert saved["default_processing_mode"] == "ai_illustration"
    assert saved["sharpen_percent"] == 35 and saved["jpeg_quality"] == 82

    # Restart: the controls show the saved values ...
    w2 = new_window()
    cv2 = w2.controls_view
    assert cv2.rb_illustration.isChecked()
    assert cv2.rb_jpg.isChecked() and cv2.jpeg_options_widget.isVisibleTo(cv2)
    assert cv2.get_dpi() == 500 and cv2.btn_dpi_500.isChecked()
    assert cv2.slider_sharpen.value() == 35 and cv2.lbl_sharp_val.text() == "35%"
    assert cv2.slider_jpeg_q.value() == 82 and cv2.lbl_jpeg_q_val.text() == "82"
    assert cv2.get_jpeg_bg_color() == (10, 20, 30)
    assert cv2.get_composition_mode().value == "crop"

    # ... the job parameters agree with them ...
    src = tmp_path / "art.png"
    arr = np.zeros((60, 80, 4), np.uint8)
    arr[..., :3] = (200, 60, 40)
    arr[..., 3] = 255
    arr[:, :10, 3] = 0
    Image.fromarray(arr, "RGBA").save(src)
    w2.queue_view.add_files([str(src)])
    params = w2._build_job_params(str(src), str(tmp_path / "x.jpg"), overwrite=False)
    assert (params.dpi, params.output_format, params.processing_mode, params.sharpen_percent, params.jpeg_quality) == \
        (500, "JPEG", ProcessingMode.AI_ILLUSTRATION, 35, 82)

    # ... and a real export uses them
    out = str(tmp_path / "restored.jpg")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    w2._export_selected_image()
    assert wait_until(qapp, lambda: w2._active_worker is None and w2.last_export_result is not None)
    res = w2.last_export_result
    assert res.success, res.error_message
    assert "AI Illustration" in res.method_used and "unsharp mask 35%" in res.method_used
    with Image.open(res.output_path) as im:
        assert im.format == "JPEG" and im.size == (160, 120)
        assert abs(im.info["dpi"][0] - 500) < 0.03
        # Quantisation tables identify the encoder quality independently of the app
        ref = io.BytesIO()
        Image.new("RGB", (16, 16)).save(ref, "JPEG", quality=82, subsampling=0)
        assert im.quantization == Image.open(ref).quantization
    close(w2, qapp)


def test_startup_does_not_overwrite_saved_preferences(qapp, profile):
    profile.parent.mkdir(parents=True, exist_ok=True)
    data = {"theme": "light", "default_dpi": 600, "default_format": "JPEG", "default_processing_mode": "ai_photo",
            "sharpen_percent": 12, "jpeg_quality": 91, "prefer_gpu": False, "last_output_dir": "D:\\Exports"}
    profile.write_text(json.dumps(data), encoding="utf-8")
    before = profile.read_bytes()
    w = new_window()
    pump(qapp, 1.0)  # longer than the 400 ms save debounce
    assert profile.read_bytes() == before, "start-up must not rewrite the user's settings"
    cv = w.controls_view
    assert cv.rb_photo.isChecked() and cv.rb_jpg.isChecked() and cv.get_dpi() == 600
    assert cv.slider_sharpen.value() == 12 and cv.slider_jpeg_q.value() == 91
    assert not cv.chk_gpu.isChecked() and w.engine.prefer_gpu is False
    assert w.config.theme == "light" and w.act_theme.isChecked()
    close(w, qapp)
    after = json.loads(profile.read_text(encoding="utf-8"))
    assert after["last_output_dir"] == "D:\\Exports"  # user's output folder is preserved


def test_invalid_values_fall_back_individually(qapp, profile):
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(json.dumps({
        "default_dpi": "abc", "default_format": "TIFF", "default_processing_mode": "magic",
        "sharpen_percent": 500, "jpeg_quality": 88, "prefer_gpu": "yes", "theme": "neon",
        "window_geometry": [99999, 99999, 5000, 4000], "future_option": 1}), encoding="utf-8")
    w = new_window()
    cv = w.controls_view
    assert cv.get_dpi() == 300 and cv.rb_png.isChecked() and cv.rb_preserve.isChecked()
    assert cv.slider_sharpen.value() == 0
    assert cv.slider_jpeg_q.value() == 88  # the valid value is kept
    assert cv.chk_gpu.isChecked() and w.config.theme == "dark"
    avail = w.screen().availableGeometry()
    g = w.geometry()
    assert avail.contains(g.topLeft()) and g.width() <= avail.width() and g.height() <= avail.height()
    close(w, qapp)


def test_metadata_only_is_not_restored(qapp, profile):
    w = new_window()
    w.controls_view.rb_dim_meta.setChecked(True)
    close(w, qapp)
    w2 = new_window()
    assert w2.controls_view.get_dimension_mode() == DimensionMode.PIXEL_DIMS
    assert w2.controls_view._export_frame.isEnabled()
    close(w2, qapp)


@pytest.mark.parametrize("mode", ["preserve_artwork", "ai_illustration"])
def test_crop_preview_matches_export_region(qapp, profile, tmp_path, monkeypatch, mode):
    """U-6: the preview is processed with 32 px of real surrounding context, so it should match the
    same region of the full export closely (remaining differences: sub-pixel resampling phase)."""
    rng = np.random.default_rng(7)
    tex = (rng.random((50, 50)) > 0.5).astype(np.uint8) * 255
    tex = np.kron(tex, np.ones((6, 6), np.uint8))
    arr = np.dstack([tex, 255 - tex, tex // 2, np.full_like(tex, 255)])
    src = tmp_path / "texture.png"
    Image.fromarray(arr, "RGBA").save(src)

    w = new_window()
    cv = w.controls_view
    {"preserve_artwork": cv.rb_preserve, "ai_illustration": cv.rb_illustration}[mode].setChecked(True)
    cv.rb_dim_pixel.setChecked(True)
    cv.chk_lock_aspect.setChecked(False)
    cv.spin_px_w.setValue(1200)
    cv.spin_px_h.setValue(1200)
    w.queue_view.add_files([str(src)])
    w._generate_crop_preview()
    assert wait_until(qapp, lambda: w._active_worker is None and w.last_preview_info is not None)
    info = w.last_preview_info
    rx0, ry0, rx1, ry1 = info["region"]
    assert (rx0, ry0, rx1, ry1) != (0, 0, 300, 300), "the region must be a crop, not the whole image"

    out = str(tmp_path / "full.png")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    w._export_selected_image()
    assert wait_until(qapp, lambda: w._active_worker is None and w.last_export_result is not None)
    full = np.array(Image.open(w.last_export_result.output_path).convert("RGBA")).astype(int)
    prev = np.array(info["image"]).astype(int)
    s = 1200 / 300
    region = full[int(ry0 * s):int(ry0 * s) + prev.shape[0], int(rx0 * s):int(rx0 * s) + prev.shape[1]]
    assert region.shape == prev.shape
    diff = np.abs(region - prev)[..., :3]
    assert diff.mean() < 1.0, f"preview differs from export region: mean {diff.mean():.2f}"
    assert np.percentile(diff, 99.9) <= 8
    close(w, qapp)
