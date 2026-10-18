"""
GUI workflow regression tests. They drive the real MainWindow (offscreen Qt platform) through
its own slots, so settings travel through the same code path as user clicks. Native file
dialogs and modal message boxes are replaced with stubs; everything else is the shipped code.
"""

import os
import time
import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from printscale.core.pipeline import CANCELLED_MESSAGE  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    # Keep the user's real %APPDATA% config untouched
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    from printscale.ui import main_window as mw
    monkeypatch.setattr(mw.BatchSummaryDialog, "exec", lambda self: 0)
    monkeypatch.setattr(mw.SummaryDialog, "exec", lambda self: 0)
    win = mw.MainWindow()
    yield win
    if win._active_worker is not None:
        win._active_worker.cancel()
        win._active_worker.wait(60000)
    win.is_auto_test = True
    win.close()  # stops the debounced settings save before the next test's profile is active
    win.deleteLater()


def wait_until(qapp, predicate, timeout=180.0):
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def make_png(path, size=(120, 90), alpha=True):
    arr = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    arr[..., 0] = 220
    arr[..., 3] = 255
    if alpha:
        arr[:, : size[0] // 3, 3] = 0
        arr[:, size[0] // 3: size[0] // 2, 3] = 128
    Image.fromarray(arr, "RGBA").save(path)
    return str(path)


def test_batch_export_uses_print_size_settings(window, qapp, tmp_path, monkeypatch):
    """Regression: v1.0.1 batch export ignored the entered print size and used 14 x 16 in."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    files = [make_png(src_dir / f"art_{i}.png") for i in range(2)]
    window.queue_view.add_files(files)

    cv = window.controls_view
    cv.chk_lock_aspect.setChecked(False)
    cv.rb_dim_print.setChecked(True)
    cv.combo_unit.setCurrentText("in")
    cv.spin_print_w.setValue(2.0)
    cv.spin_print_h.setValue(3.0)
    cv.btn_dpi_400.click()
    assert cv.get_dpi() == 400

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(out_dir)))
    window._export_all_queue()
    assert wait_until(qapp, lambda: window._active_worker is None and not window._batch_queue
                      and len(window._batch_results) == 2)

    for src, res in window._batch_results:
        assert res.success, res.error_message
        with Image.open(res.output_path) as im:
            assert im.size == (800, 1200)  # 2 x 3 in at 400 DPI
            assert abs(im.info["dpi"][0] - 400) < 0.03


def test_batch_cancel_stops_remaining_items(window, qapp, tmp_path, monkeypatch):
    """Regression: v1.0.1 Cancel only stopped the current item and the batch carried on."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    files = [make_png(src_dir / f"big_{i}.png", size=(600, 600), alpha=False) for i in range(3)]
    window.queue_view.add_files(files)
    cv = window.controls_view
    cv.rb_photo.setChecked(True)  # AI photo: slow enough to cancel mid-batch
    cv.rb_dim_pixel.setChecked(True)
    cv.chk_lock_aspect.setChecked(False)
    cv.spin_px_w.setValue(2400)
    cv.spin_px_h.setValue(2400)

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(out_dir)))
    window._export_all_queue()
    # Cancel while the first item is inside AI inference (progress band 30-82%)
    assert wait_until(qapp, lambda: window._active_worker is not None
                      and window.status_bar_view.progress_bar.value() > 31, 120)
    window._cancel_processing()
    assert wait_until(qapp, lambda: window._active_worker is None and len(window._batch_results) == 3)

    statuses = [r.error_message == CANCELLED_MESSAGE for _, r in window._batch_results]
    assert statuses[0], "the item being processed must stop at the next tile boundary"
    assert all(statuses[1:]), "items after the cancelled one must not run"
    written = [n for n in os.listdir(out_dir) if not n.startswith(".")]
    temp_left = [n for n in os.listdir(out_dir) if n.startswith(".printscale_")]
    assert temp_left == []
    # At most the first item can have completed before the cancel landed
    assert len(written) <= 1


def test_metadata_only_keeps_source_format_and_pixels(window, qapp, tmp_path, monkeypatch):
    """Regression: v1.0.1 wrote PNG bytes into a .jpg file when JPEG was selected in metadata-only mode."""
    src = make_png(tmp_path / "logo.png")
    window.queue_view.add_files([src])
    cv = window.controls_view
    cv.rb_jpg.setChecked(True)
    cv.rb_dim_meta.setChecked(True)
    cv.btn_dpi_600.click()

    target = {}

    def fake_save(parent, caption, default, flt):
        target["default"] = default
        return default, flt

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake_save))
    window._export_selected_image()
    assert wait_until(qapp, lambda: window._active_worker is None and window.last_export_result is not None)
    res = window.last_export_result
    assert res.success, res.error_message
    assert target["default"].endswith(".png")
    with Image.open(res.output_path) as out, Image.open(src) as orig:
        assert out.format == "PNG"
        assert abs(out.info["dpi"][0] - 600) < 0.03
        assert out.tobytes() == orig.tobytes()


def test_preview_refused_while_export_running(window, qapp, tmp_path, monkeypatch):
    """Regression: v1.0.1 let the crop preview start a second worker and orphan the running export."""
    src = make_png(tmp_path / "photo.png", size=(700, 700), alpha=False)
    window.queue_view.add_files([src])
    cv = window.controls_view
    cv.rb_photo.setChecked(True)
    cv.rb_dim_pixel.setChecked(True)
    cv.chk_lock_aspect.setChecked(False)
    cv.spin_px_w.setValue(2800)
    cv.spin_px_h.setValue(2800)
    out = str(tmp_path / "photo_out.png")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    window._export_selected_image()
    running = window._active_worker
    assert running is not None
    assert wait_until(qapp, lambda: window.status_bar_view.progress_bar.value() > 31, 120)
    window._generate_crop_preview()
    assert window._active_worker is running, "a second job must not replace the running one"
    assert not window.preview_view.btn_crop_preview.isEnabled()
    window._cancel_processing()
    assert wait_until(qapp, lambda: window._active_worker is None)
    assert window.last_export_result.error_message == CANCELLED_MESSAGE
    assert not os.path.exists(out)


def test_crop_preview_and_before_after_registration(window, qapp, tmp_path, monkeypatch):
    """Crop preview runs the real pipeline; after export the 'before' image is placed with the export's
    own fit/pad geometry so both sides share coordinates."""
    src = make_png(tmp_path / "wide.png", size=(200, 100), alpha=False)
    window.queue_view.add_files([src])
    cv = window.controls_view
    cv.rb_preserve.setChecked(True)
    cv.rb_dim_pixel.setChecked(True)
    cv.chk_lock_aspect.setChecked(False)
    cv.spin_px_w.setValue(400)
    cv.spin_px_h.setValue(400)

    window._generate_crop_preview()
    assert wait_until(qapp, lambda: window._active_worker is None)
    assert window.status_bar_view.lbl_stage.text().startswith("Preview ready")
    assert window.last_preview_info is not None and window.last_preview_info["size"][0] > 0

    out = str(tmp_path / "wide_out.png")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    window._export_selected_image()
    assert wait_until(qapp, lambda: window._active_worker is None and window.last_export_result is not None)
    res = window.last_export_result
    assert res.success and (res.target_width, res.target_height) == (400, 400)
    registered = window._registered_original(400, 400, window._export_params)
    a = np.array(registered)[..., 3]
    b = np.array(Image.open(res.output_path).convert("RGBA"))[..., 3]
    assert a.shape == b.shape == (400, 400)
    assert np.array_equal(a > 0, b > 0), "before/after content areas must coincide"


def test_side_by_side_zoomed_panes_both_render(qapp):
    """Visible-GUI defect found in 1.0.3: when zoomed in, the right pane's background fill replaced the
    painter clip and painted over the left pane, so ORIGINAL showed only background."""
    from printscale.ui.preview_view import ViewportCanvas
    c = ViewportCanvas()
    c.resize(960, 700)
    c.show()
    img = Image.new("RGBA", (4200, 4800), (255, 255, 255, 255))
    c.set_images(img, img)
    c.set_view_mode("side_by_side")
    c.set_bg_mode("black")
    c.set_zoom_level(1.0)   # right image rect now extends over the left half
    qapp.processEvents()
    arr = np.array(Image.fromqimage(c.grab().toImage()).convert("L")).astype(int) if hasattr(Image, "fromqimage") else None
    if arr is None:
        import io as _io
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.ReadWrite)
        c.grab().save(buf, "PNG")
        arr = np.array(Image.open(_io.BytesIO(bytes(buf.data()))).convert("L")).astype(int)
    h, w = arr.shape
    left, right = arr[h // 4: 3 * h // 4, 20: w // 2 - 20], arr[h // 4: 3 * h // 4, w // 2 + 20: w - 20]
    assert left.mean() > 200 and right.mean() > 200, (left.mean(), right.mean())
    c.close()


def test_toolbar_overflow_button_has_usable_width(qapp):
    """Visible-GUI defect D3: at narrow widths the toolbar's overflow button was squeezed to ~12 px."""
    from PySide6.QtWidgets import QToolButton
    from printscale.ui.style import PrintScaleStyle
    from printscale.ui.preview_view import PreviewView
    old = qapp.style().name() if hasattr(qapp.style(), "name") else None
    qapp.setStyle(PrintScaleStyle())
    try:
        v = PreviewView()
        v.resize(330, 400)
        v.show()
        qapp.processEvents()
        ext = v.toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
        assert ext is not None and ext.isVisible(), "toolbar should overflow at this width"
        assert ext.width() >= 24, ext.width()
        v.close()
    finally:
        qapp.setStyle("Fusion")


def test_cancel_keeps_pane_labels(window, qapp):
    """Visible-GUI defect D2: a cancelled job relabelled the still-visible preview panes."""
    c = window.preview_view.canvas
    c.set_caption("Preview · source x 0–10", ("SOURCE (nearest)", "PREVIEW"))
    c.set_caption("Preview cancelled")
    assert c._labels == ("SOURCE (nearest)", "PREVIEW")
