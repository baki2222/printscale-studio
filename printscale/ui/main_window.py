"""
PrintScale Studio - Main Desktop Window
Layout: Images panel | comparison viewer | Settings panel (resizable splitter), with the job
status/export bar below. Panels can be hidden from the viewer toolbar or View menu; at narrow
widths the Images panel collapses automatically so the viewer keeps a usable size.
"""

import os
import tempfile
from typing import Optional, List, Tuple
from PIL import Image

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRect
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QSplitter, QFileDialog, QMessageBox
)
from PySide6.QtGui import QAction, QKeySequence, QGuiApplication

from printscale import __version__
from printscale.core.geometry import (
    DimensionMode, CompositionMode, plan_canvas_sizing
)
from printscale.core.metadata import read_file_metadata, normalize_image_orientation
from printscale.core.pipeline import (
    JobParameters, JobExecutionResult, execute_pipeline, CANCELLED_MESSAGE
)
from printscale.core.config import load_config, save_config
from printscale.core.batch import generate_collision_safe_filename
from printscale.inference.engine import InferenceEngine

from printscale.ui.queue_view import QueueView
from printscale.ui.preview_view import PreviewView
from printscale.ui.controls_view import ControlsView
from printscale.ui.status_bar import StatusBarView
from printscale.ui.summary_dialog import SummaryDialog, BatchSummaryDialog
from printscale.ui.theme import build_stylesheet, build_qpalette, palette_for
from printscale.ui.icons import make_icon
from printscale.ui.branding import app_icon, render_logo


# Larger canvases are downsampled for on-screen comparison only (exports are never affected)
PREVIEW_MAX_PIXELS = 64_000_000
# Below this window width (logical px) the Images panel collapses automatically
COMPACT_WIDTH = 1080
# Source context added around a crop preview (matches the AI tile context)
PREVIEW_CONTEXT_PX = 32

STATUS_OK, STATUS_BUSY, STATUS_ERR, STATUS_WARN = "#34c38f", "#f0a43a", "#f0606a", "#f0a43a"


class PipelineWorker(QThread):
    progress = Signal(int, int, str)
    job_finished = Signal(object)  # JobExecutionResult

    def __init__(self, params: JobParameters, engine: InferenceEngine):
        super().__init__()
        self.params = params
        self.engine = engine
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        def progress_cb(cur: int, tot: int, msg: str):
            self.progress.emit(cur, tot, msg)

        def is_cancelled():
            return self._cancelled

        try:
            result = execute_pipeline(
                params=self.params,
                engine=self.engine,
                progress_callback=progress_cb,
                is_cancelled_callback=is_cancelled
            )
        except Exception as e:  # never let a worker die silently
            result = JobExecutionResult(
                success=False, output_path=self.params.output_path, target_width=0, target_height=0,
                output_dpi=0, physical_width_in=0, physical_height_in=0, file_size_bytes=0,
                has_alpha=False, format=self.params.output_format, method_used="", device_used="",
                verification_passed=False, error_message=f"Unexpected error: {e}"
            )
        self.job_finished.emit(result)


def _failed(message: str) -> JobExecutionResult:
    return JobExecutionResult(
        success=False, output_path="", target_width=0, target_height=0, output_dpi=0,
        physical_width_in=0, physical_height_in=0, file_size_bytes=0, has_alpha=False,
        format="", method_used="", device_used="", verification_passed=False, error_message=message)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PrintScale Studio {__version__}")
        self.setWindowIcon(app_icon())

        self.config = load_config()
        self.engine = InferenceEngine(prefer_gpu=self.config.prefer_gpu)
        self._active_worker: Optional[PipelineWorker] = None
        self._active_kind: Optional[str] = None  # 'export', 'batch' or 'preview'
        self._current_filepath: Optional[str] = None
        self._loaded_original_img: Optional[Image.Image] = None
        self._batch_queue: List[str] = []
        self._batch_results: List[Tuple[str, JobExecutionResult]] = []
        self._batch_cancelled = False
        self._batch_current: Optional[str] = None
        self._export_params: Optional[JobParameters] = None
        self._preview_ctx = None
        self._view_plan = None          # SizingPlan of the export currently shown, if any
        self._auto_collapsed = False
        self._closing_saved = False
        self.is_auto_test = False
        self.last_export_result: Optional[JobExecutionResult] = None
        self.last_preview_info = None

        self._build_ui()
        self._setup_menus()
        self._apply_theme(self.config.theme, save=False)

        # Saved preferences are applied before any save can be triggered (U-5)
        self.controls_view.apply_preferences(self.config)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save_preferences)
        self.controls_view.preferences_changed.connect(self._save_timer.start)

        self.status_bar_view.set_device_info(self.engine.device_description)
        self._restore_geometry()
        self._update_inputs_available()

    # ------------------------------------------------------------------ construction
    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 6, 8, 8)
        main_layout.setSpacing(8)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setHandleWidth(8)
        self.splitter.setChildrenCollapsible(False)

        self.queue_view = QueueView(self.splitter)
        self.preview_view = PreviewView(self.splitter)
        self.preview_view.setMinimumWidth(300)
        self.controls_view = ControlsView(self.splitter)
        for w in (self.queue_view, self.preview_view, self.controls_view):
            self.splitter.addWidget(w)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        main_layout.addWidget(self.splitter, 1)

        self.status_bar_view = StatusBarView(self)
        main_layout.addWidget(self.status_bar_view)

        self.queue_view.image_selected.connect(self._on_image_selected)
        self.queue_view.files_added.connect(self._on_files_added)
        self.queue_view.selection_cleared.connect(self._on_selection_cleared)
        self.controls_view.prefer_gpu_changed.connect(self._on_prefer_gpu_changed)
        self.preview_view.crop_preview_requested.connect(self._generate_crop_preview)
        self.preview_view.canvas.files_dropped.connect(self._on_viewer_drop)
        self.preview_view.toggle_queue_requested.connect(lambda: self._set_queue_visible(self.preview_view.act_toggle_queue.isChecked(), user=True))
        self.preview_view.toggle_settings_requested.connect(lambda: self._set_settings_visible(self.preview_view.act_toggle_settings.isChecked()))

        self.status_bar_view.export_selected_clicked.connect(lambda: self._export_selected_image())
        self.status_bar_view.export_all_clicked.connect(self._export_all_queue)
        self.status_bar_view.cancel_clicked.connect(self._cancel_processing)

    def _setup_menus(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        self.act_add = QAction("&Add Images…", self)
        self.act_add.setShortcut(QKeySequence.StandardKey.Open)
        self.act_add.triggered.connect(self.queue_view._browse_and_add)
        file_menu.addAction(self.act_add)
        self.act_export = QAction("&Export Selected…", self)
        self.act_export.setShortcut("Ctrl+E")
        self.act_export.triggered.connect(lambda: self._export_selected_image())
        file_menu.addAction(self.act_export)
        self.act_export_all = QAction("Export &Queue…", self)
        self.act_export_all.setShortcut("Ctrl+Shift+E")
        self.act_export_all.triggered.connect(self._export_all_queue)
        file_menu.addAction(self.act_export_all)
        file_menu.addSeparator()
        act_exit = QAction("E&xit", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        view_menu = menubar.addMenu("&View")
        self.act_menu_queue = QAction("&Images Panel", self)
        self.act_menu_queue.setCheckable(True)
        self.act_menu_queue.setChecked(True)
        self.act_menu_queue.setShortcut("Ctrl+Shift+I")
        self.act_menu_queue.triggered.connect(lambda on: self._set_queue_visible(on, user=True))
        view_menu.addAction(self.act_menu_queue)
        self.act_menu_settings = QAction("&Settings Panel", self)
        self.act_menu_settings.setCheckable(True)
        self.act_menu_settings.setChecked(True)
        self.act_menu_settings.setShortcut("Ctrl+Shift+S")
        self.act_menu_settings.triggered.connect(self._set_settings_visible)
        view_menu.addAction(self.act_menu_settings)
        view_menu.addSeparator()
        for text, key, slot in (("Zoom to &Fit", "Ctrl+0", self.preview_view.canvas.zoom_to_fit),
                                ("Zoom &100% (output pixels)", "Ctrl+1", lambda: self.preview_view.canvas.set_output_zoom(1.0)),
                                ("Zoom &200%", "Ctrl+2", lambda: self.preview_view.canvas.set_output_zoom(2.0))):
            a = QAction(text, self)
            a.setShortcut(key)
            a.triggered.connect(slot)
            view_menu.addAction(a)
        view_menu.addSeparator()
        self.act_theme = QAction("&Light Theme", self)
        self.act_theme.setCheckable(True)
        self.act_theme.triggered.connect(lambda on: self._apply_theme("light" if on else "dark"))
        view_menu.addAction(self.act_theme)

        help_menu = menubar.addMenu("&Help")
        for text, slot in (("Print DPI and Pixels", self._show_dpi_guide), ("Upload Profile Limits", self._show_upload_preset_guide),
                           ("&About PrintScale Studio", self._show_about_dialog)):
            a = QAction(text, self)
            a.triggered.connect(slot)
            help_menu.addAction(a)

    # ------------------------------------------------------------------ theme
    def _apply_theme(self, theme_name: str, save: bool = True):
        p = palette_for(theme_name)
        app = QApplication.instance()
        app.setPalette(build_qpalette(p))
        app.setStyleSheet(build_stylesheet(p))
        self.config.theme = p["name"]
        self.act_theme.setChecked(p["name"] == "light")
        self.preview_view.canvas.set_theme(p)
        icon = lambda n: make_icon(n, p["muted"] if n in ("chevron_right", "chevron_down") else p["text"], p["disabled"])
        icons = {n: icon(n) for n in ("add", "remove", "clear", "split", "sidebyside", "fit", "crop", "export", "queue",
                                      "cancel", "panel_left", "panel_right", "more", "chevron_right", "chevron_down")}
        icons["export"] = make_icon("export", p["accent_text"], p["disabled"])
        icons["cancel"] = make_icon("cancel", p["danger"], p["disabled"])
        self.preview_view.set_icons(icons)
        self.status_bar_view.set_icons(icons)
        self.queue_view.set_icons(icons["add"], icons["remove"], icons["clear"], make_icon("drop", p["faint"], size=36))
        self.controls_view.set_section_icons(icons["chevron_right"], icons["chevron_down"])
        if save:
            save_config(self.config)

    def _toggle_theme(self):
        self._apply_theme("light" if self.config.theme == "dark" else "dark")

    # ------------------------------------------------------------------ geometry and panels
    def _available_rect(self) -> QRect:
        screen = self.screen() or QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)

    def _restore_geometry(self):
        avail = self._available_rect()
        self.setMinimumSize(min(720, avail.width()), min(460, avail.height()))
        g = self.config.window_geometry
        if g:
            x, y, w, h = g
            w, h = min(w, avail.width()), min(h, avail.height())
            # Keep the restored window fully on the current desktop
            x = max(avail.left(), min(x, avail.right() - w + 1))
            y = max(avail.top(), min(y, avail.bottom() - h + 1))
            self.setGeometry(x, y, w, h)
        else:
            w = min(int(avail.width() * 0.92), 1560)
            h = min(int(avail.height() * 0.92), 980)
            self.setGeometry(avail.left() + (avail.width() - w) // 2, avail.top() + (avail.height() - h) // 2, w, h)
        sizes = self.config.splitter_sizes
        if sizes and sum(sizes) > 0:
            self.splitter.setSizes(sizes)
        else:
            self.splitter.setSizes([250, max(400, self.width() - 600), 330])
        self._set_settings_visible(self.config.settings_panel_visible)
        self._set_queue_visible(self.config.queue_panel_visible, user=False)
        if self.config.window_maximized:
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def _set_queue_visible(self, visible: bool, user: bool = False):
        self.queue_view.setVisible(visible)
        self.preview_view.act_toggle_queue.setChecked(visible)
        self.act_menu_queue.setChecked(visible)
        if user:
            self._auto_collapsed = False
            self.config.queue_panel_visible = visible

    def _set_settings_visible(self, visible: bool):
        self.controls_view.setVisible(visible)
        self.preview_view.act_toggle_settings.setChecked(visible)
        self.act_menu_settings.setChecked(visible)
        self.config.settings_panel_visible = visible

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Compact layout: give the viewer room by collapsing the Images panel; restore it when wide again
        if self.width() < COMPACT_WIDTH and not self.queue_view.isHidden() and not self._auto_collapsed:
            self._auto_collapsed = True
            self._set_queue_visible(False)
        elif self.width() >= COMPACT_WIDTH + 40 and self._auto_collapsed:
            self._auto_collapsed = False
            self._set_queue_visible(True)

    def _save_preferences(self):
        self.controls_view.collect_preferences(self.config)
        save_config(self.config)

    def _save_window_state(self):
        self.config.window_maximized = self.isMaximized()
        g = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.config.window_geometry = [g.x(), g.y(), g.width(), g.height()]
        sizes = self.splitter.sizes()
        if all(s > 0 for s in sizes):
            self.config.splitter_sizes = sizes
        if not self._auto_collapsed:
            self.config.queue_panel_visible = not self.queue_view.isHidden()

    # ------------------------------------------------------------------ state helpers
    def _is_busy(self, notify: bool = True) -> bool:
        busy = self._active_worker is not None
        if busy and notify and not self.is_auto_test:
            QMessageBox.warning(self, "Job running", "A job is already running. Wait for it to finish or cancel it.")
        return busy

    def _update_inputs_available(self):
        has_queue = len(self.queue_view.get_all_filepaths()) > 0
        has_sel = self._current_filepath is not None
        self.status_bar_view.set_inputs_available(has_sel, has_queue)
        self.act_export.setEnabled(has_sel and self._active_worker is None)
        self.act_export_all.setEnabled(has_queue and self._active_worker is None)
        self.preview_view.set_actions_enabled(has_sel and self._active_worker is None)

    def _start_worker(self, params: JobParameters, kind: str, on_finished):
        self._active_kind = kind
        self.status_bar_view.set_running_state(True)
        self.queue_view.set_editing_enabled(False)
        self.controls_view.set_hardware_toggle_enabled(False)
        worker = PipelineWorker(params, self.engine)
        worker.progress.connect(self._on_worker_progress)
        worker.job_finished.connect(on_finished)
        self._active_worker = worker
        self._update_inputs_available()
        worker.start()

    def _worker_done(self):
        worker = self._active_worker
        self._active_worker = None
        self._active_kind = None
        if worker is not None:
            worker.wait()
        self.status_bar_view.set_running_state(False)
        self.queue_view.set_editing_enabled(True)
        self.controls_view.set_hardware_toggle_enabled(True)
        self._update_inputs_available()

    def _output_extension(self, source_path: str) -> str:
        """Metadata-only output keeps the source encoding; other modes follow the chosen format."""
        if self.controls_view.get_dimension_mode() == DimensionMode.METADATA_ONLY:
            ext = os.path.splitext(source_path)[1].lower()
            return "jpg" if ext in (".jpg", ".jpeg") else ext.lstrip(".")
        return "png" if self.controls_view.get_output_format() == "PNG" else "jpg"

    def _target_dimensions_for(self, source_path: str) -> Tuple[int, int]:
        if self.controls_view.get_dimension_mode() == DimensionMode.METADATA_ONLY:
            meta = read_file_metadata(source_path)
            return meta.width, meta.height
        return self.controls_view.get_target_dimensions()

    def _build_job_params(self, source_path: str, out_path: str, overwrite: bool) -> JobParameters:
        """Single source of truth for turning the current controls into frozen job parameters."""
        cv = self.controls_view
        target_w, target_h = cv.get_target_dimensions()
        return JobParameters(
            source_path=source_path,
            output_path=out_path,
            output_format=cv.get_output_format(),
            dimension_mode=cv.get_dimension_mode(),
            dpi=cv.get_dpi(),
            print_width=cv.spin_print_w.value(),
            print_height=cv.spin_print_h.value(),
            print_unit=cv.get_print_unit(),
            pixel_width=target_w,
            pixel_height=target_h,
            processing_mode=cv.get_processing_mode(),
            composition_mode=cv.get_composition_mode(),
            crop_alignment=cv.get_crop_alignment(),
            sharpen_percent=cv.get_sharpen_percent(),
            jpeg_quality=cv.get_jpeg_quality(),
            jpeg_bg_color=cv.get_jpeg_bg_color(),
            prefer_gpu=self.config.prefer_gpu,
            overwrite_existing=overwrite
        )

    # ------------------------------------------------------------------ queue/selection
    def _on_files_added(self, filepaths: List[str]):
        if filepaths and not self._current_filepath:
            self._on_image_selected(filepaths[0])
        self._update_inputs_available()

    def _on_viewer_drop(self, paths: List[str]):
        if self._active_worker is None:
            self.queue_view.add_files(paths)

    def _on_selection_cleared(self):
        self._current_filepath = None
        self._loaded_original_img = None
        self._view_plan = None
        self.controls_view.set_metadata(None)
        self.preview_view.set_images(None, None)
        self.preview_view.canvas.set_caption("")
        self.status_bar_view.set_stage("Ready")
        self._update_inputs_available()

    def _on_image_selected(self, filepath: str):
        self._current_filepath = filepath
        try:
            meta = read_file_metadata(filepath)
            self.controls_view.set_metadata(meta)
            with Image.open(filepath) as im:
                im = normalize_image_orientation(im)
                if im.mode != "RGBA":
                    im = im.convert("RGBA")
                self._loaded_original_img = im.copy()
            self._view_plan = None
            self.preview_view.set_images(self._loaded_original_img, None)
            self.preview_view.canvas.set_caption(f"Original · {os.path.basename(filepath)}", ("ORIGINAL", "RESULT"))
            self.status_bar_view.set_stage(f"Loaded {os.path.basename(filepath)}")
        except Exception as e:
            self._loaded_original_img = None
            self.status_bar_view.set_stage(f"Could not load {os.path.basename(filepath)}: {e}", error=True)
            QMessageBox.critical(self, "Could not load image", f"{filepath}\n\n{e}")
        self._update_inputs_available()

    def _on_prefer_gpu_changed(self, prefer_gpu: bool):
        if self._is_busy(notify=False):
            return
        self.config.prefer_gpu = prefer_gpu
        save_config(self.config)
        self.engine = InferenceEngine(prefer_gpu=prefer_gpu)
        self.status_bar_view.set_device_info(self.engine.device_description)

    # ------------------------------------------------------------------ preview / comparison
    def _registered_original(self, target_w: int, target_h: int, params: JobParameters):
        """Places the original on the output canvas using the same geometry as the export,
        so before/after pixels line up (nearest-neighbour enlargement shows true source pixels)."""
        orig = self._loaded_original_img
        if orig is None:
            return None
        if params.dimension_mode == DimensionMode.METADATA_ONLY:
            return orig
        plan = plan_canvas_sizing(orig.width, orig.height, target_w, target_h,
                                  params.composition_mode, params.crop_alignment)
        scaled = orig.resize((plan.scaled_content_w, plan.scaled_content_h), resample=Image.Resampling.NEAREST)
        if plan.composition == CompositionMode.CROP:
            return scaled.crop(plan.crop_box)
        canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        canvas.paste(scaled, (plan.offset_x, plan.offset_y))
        return canvas

    def _show_comparison(self, original: Optional[Image.Image], processed: Image.Image):
        """Shows before/after; very large canvases are downsampled for display only."""
        out_w, out_h = processed.size
        display_scale = 1.0
        if out_w * out_h > PREVIEW_MAX_PIXELS:
            display_scale = (PREVIEW_MAX_PIXELS / float(out_w * out_h)) ** 0.5
            size = (max(1, int(out_w * display_scale)), max(1, int(out_h * display_scale)))
            processed = processed.resize(size, Image.Resampling.BOX)
            if original is not None:
                original = original.resize(size, Image.Resampling.NEAREST)
        self.preview_view.set_images(original, processed, output_size=(out_w, out_h), display_scale=display_scale)

    def _preview_center_in_source(self) -> Tuple[float, float]:
        """Source-pixel coordinates under the centre of the viewer (falls back to the image centre)."""
        src_w, src_h = self._loaded_original_img.size
        frac = self.preview_view.canvas.viewport_center_in_image()
        if frac is None:
            return src_w / 2.0, src_h / 2.0
        fx, fy = frac
        plan = self._view_plan
        if plan is None:
            return fx * src_w, fy * src_h
        # Viewer shows an export canvas: map canvas pixels back to source pixels
        if plan.composition == CompositionMode.CROP:
            cx = fx * plan.target_canvas_w + plan.crop_box[0]
            cy = fy * plan.target_canvas_h + plan.crop_box[1]
        else:
            cx = fx * plan.target_canvas_w - plan.offset_x
            cy = fy * plan.target_canvas_h - plan.offset_y
        return (min(src_w, max(0.0, cx / plan.scale_factor_x)), min(src_h, max(0.0, cy / plan.scale_factor_y)))

    def _generate_crop_preview(self):
        """Processes the source region under the viewer centre with the real pipeline and current
        settings. The region is padded with PREVIEW_CONTEXT_PX of real surrounding source pixels
        (the same context the tiled AI export uses); that margin is discarded afterwards."""
        if not self._current_filepath or not self._loaded_original_img:
            if not self.is_auto_test:
                QMessageBox.information(self, "No image", "Add and select an image first.")
            return
        if self._is_busy():
            return
        if self.controls_view.get_dimension_mode() == DimensionMode.METADATA_ONLY:
            QMessageBox.information(self, "Preview", "DPI metadata only does not change pixels, so there is nothing to preview.")
            return

        target_w, target_h = self.controls_view.get_target_dimensions()
        src_w, src_h = self._loaded_original_img.size
        plan = plan_canvas_sizing(src_w, src_h, target_w, target_h, self.controls_view.get_composition_mode(),
                                  self.controls_view.get_crop_alignment())
        scale = plan.scaled_content_w / src_w  # same content scale the export uses

        # Region size: about 1024 output pixels across, limited to the source
        region = int(max(32, min(512, round(1024 / max(scale, 1e-6)))))
        rw, rh = min(region, src_w), min(region, src_h)
        cx, cy = self._preview_center_in_source()
        rx0 = int(min(max(0, round(cx - rw / 2)), src_w - rw))
        ry0 = int(min(max(0, round(cy - rh / 2)), src_h - rh))
        rx1, ry1 = rx0 + rw, ry0 + rh
        ex0, ey0 = max(0, rx0 - PREVIEW_CONTEXT_PX), max(0, ry0 - PREVIEW_CONTEXT_PX)
        ex1, ey1 = min(src_w, rx1 + PREVIEW_CONTEXT_PX), min(src_h, ry1 + PREVIEW_CONTEXT_PX)

        with Image.open(self._current_filepath) as src:
            src = normalize_image_orientation(src)
            icc = src.info.get("icc_profile")
            expanded = src.crop((ex0, ey0, ex1, ey1))
            expanded.load()
        if expanded.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            expanded = expanded.convert("RGBA")

        tmp_dir = tempfile.mkdtemp(prefix="printscale_preview_")
        temp_src = os.path.join(tmp_dir, "crop_src.png")
        temp_dst = os.path.join(tmp_dir, "crop_dst.png")
        save_kwargs = {"format": "PNG"}
        if icc:
            save_kwargs["icc_profile"] = icc  # keep colour management identical to the export
        expanded.save(temp_src, **save_kwargs)

        out_ew = max(1, int(round((ex1 - ex0) * scale)))
        out_eh = max(1, int(round((ey1 - ey0) * scale)))
        params = self._build_job_params(temp_src, temp_dst, overwrite=True)
        params.dimension_mode = DimensionMode.PIXEL_DIMS
        params.pixel_width, params.pixel_height = out_ew, out_eh
        params.output_format = "PNG"
        params.composition_mode = CompositionMode.FIT_PAD

        sx, sy = out_ew / float(ex1 - ex0), out_eh / float(ey1 - ey0)
        keep = (int(round((rx0 - ex0) * sx)), int(round((ry0 - ey0) * sy)),
                int(round((rx1 - ex0) * sx)), int(round((ry1 - ey0) * sy)))
        region_orig = self._loaded_original_img.crop((rx0, ry0, rx1, ry1))
        self._preview_ctx = {"region": (rx0, ry0, rx1, ry1), "keep": keep, "orig": region_orig,
                             "tmp_dir": tmp_dir, "scale": scale}
        self.preview_view.canvas.set_caption(f"Preparing preview of source x {rx0}–{rx1}, y {ry0}–{ry1}…")
        self.status_bar_view.set_stage(f"Preview: processing source region {rw} × {rh} px (+{PREVIEW_CONTEXT_PX} px context)…")
        self._start_worker(params, "preview", self._on_preview_finished)

    def _on_preview_finished(self, result: JobExecutionResult):
        self._worker_done()
        ctx = self._preview_ctx
        self._preview_ctx = None
        try:
            if result.success and os.path.exists(result.output_path):
                with Image.open(result.output_path) as res_im:
                    full = res_im.convert("RGBA")
                    preview_crop = full.crop(ctx["keep"])
                registered = ctx["orig"].resize(preview_crop.size, resample=Image.Resampling.NEAREST)
                self._view_plan = None
                self._show_comparison(registered, preview_crop)
                rx0, ry0, rx1, ry1 = ctx["region"]
                self.last_preview_info = {"region": ctx["region"], "scale": ctx["scale"], "size": preview_crop.size,
                                          "image": preview_crop}
                self.preview_view.canvas.set_caption(
                    f"Preview · source x {rx0}–{rx1}, y {ry0}–{ry1} at {ctx['scale']:.2f}× (not saved)",
                    ("SOURCE (nearest)", "PREVIEW"))
                self.status_bar_view.set_stage(f"Preview ready: {result.method_used}")
                self.status_bar_view.set_device_info(result.device_used)
            elif result.error_message == CANCELLED_MESSAGE:
                self.preview_view.canvas.set_caption("Preview cancelled")
                self.status_bar_view.set_stage("Preview cancelled.")
            else:
                self.preview_view.canvas.set_caption("Preview failed")
                self.status_bar_view.set_stage(f"Preview failed: {result.error_message}", error=True)
        finally:
            tmp_dir = ctx["tmp_dir"] if ctx else None
            if tmp_dir and os.path.isdir(tmp_dir):
                for name in os.listdir(tmp_dir):
                    try:
                        os.remove(os.path.join(tmp_dir, name))
                    except OSError:
                        pass
                try:
                    os.rmdir(tmp_dir)
                except OSError:
                    pass

    # ------------------------------------------------------------------ single export
    def _export_selected_image(self, target_filepath: Optional[str] = None):
        if not self._current_filepath:
            if not self.is_auto_test:
                QMessageBox.information(self, "Export", "Select an image in the Images panel first.")
            return
        if self._is_busy():
            return

        source = self._current_filepath
        ext = self._output_extension(source)
        if target_filepath:
            out_path = target_filepath
            overwrite = False
        else:
            target_w, target_h = self._target_dimensions_for(source)
            default_dir = self.config.last_output_dir or os.path.dirname(source)
            if not os.path.isdir(default_dir):
                default_dir = os.path.dirname(source)
            stem = os.path.splitext(os.path.basename(source))[0]
            default_filename = generate_collision_safe_filename(default_dir, stem, target_w, target_h,
                                                                self.controls_view.get_dpi(), ext)
            label = "JPEG" if ext == "jpg" else ext.upper()
            out_path, _ = QFileDialog.getSaveFileName(self, "Export Selected Image", default_filename, f"{label} (*.{ext})")
            if not out_path:
                return
            out_path = os.path.normpath(out_path)  # Qt dialogs return forward slashes
            if not out_path.lower().endswith(("." + ext, ".jpeg" if ext == "jpg" else "." + ext)):
                out_path += "." + ext
            # The native save dialog has already asked the user to confirm replacing an existing file
            overwrite = True

        self.config.last_output_dir = os.path.dirname(os.path.abspath(out_path))
        save_config(self.config)

        params = self._build_job_params(source, out_path, overwrite)
        self._export_params = params
        self.queue_view.update_item_status(source, "Processing…", STATUS_BUSY)
        self.preview_view.canvas.set_caption(f"Processing {os.path.basename(source)}…")
        self.status_bar_view.set_stage(f"Exporting {os.path.basename(source)}…")
        self._start_worker(params, "export", self._on_export_finished)

    def _on_worker_progress(self, current: int, total: int, msg: str):
        prefix = {"batch": f"Batch {len(self._batch_results) + 1}/{len(self._batch_results) + len(self._batch_queue) + 1}: ",
                  "preview": "Preview: "}.get(self._active_kind, "")
        self.status_bar_view.set_stage(prefix + msg)
        self.status_bar_view.set_progress(current, total)
        # The engine picks its device when the model loads inside the job; show it as soon as it is known
        self.status_bar_view.set_device_info(self.engine.device_description)

    def _on_export_finished(self, result: JobExecutionResult):
        self._worker_done()
        params = self._export_params
        source = params.source_path if params else self._current_filepath
        self.last_export_result = result

        if result.success:
            self.status_bar_view.set_stage(f"Saved {os.path.basename(result.output_path)} · verified" if result.verification_passed
                                           else "Export saved with warnings")
            self.status_bar_view.set_device_info(result.device_used)
            self.queue_view.update_item_status(source, f"Exported · {result.target_width}×{result.target_height} px", STATUS_OK)
            # Show the saved file itself (reopened from disk) against the registered original
            try:
                with Image.open(result.output_path) as out_im:
                    proc_view = out_im.convert("RGBA")
                if source == self._current_filepath and params is not None:
                    registered = self._registered_original(result.target_width, result.target_height, params)
                    if params.dimension_mode != DimensionMode.METADATA_ONLY:
                        orig = self._loaded_original_img
                        self._view_plan = plan_canvas_sizing(orig.width, orig.height, result.target_width, result.target_height,
                                                             params.composition_mode, params.crop_alignment)
                    else:
                        self._view_plan = None
                    self._show_comparison(registered, proc_view)
                    self.preview_view.canvas.set_caption(f"Result · {os.path.basename(result.output_path)} (reopened from disk)",
                                                         ("ORIGINAL", "EXPORT"))
            except Exception as e:
                self.status_bar_view.set_stage(f"Export saved, but the preview could not be refreshed: {e}")
            if self.is_auto_test:
                QTimer.singleShot(600, self.close)
            else:
                SummaryDialog(result, self).exec()
        else:
            if result.error_message == CANCELLED_MESSAGE:
                self.status_bar_view.set_stage("Export cancelled. No file was written.")
                self.queue_view.update_item_status(source, "Cancelled", STATUS_WARN)
                self.preview_view.canvas.set_caption("Export cancelled")
            else:
                self.status_bar_view.set_stage(f"Export failed: {result.error_message}", error=True)
                self.queue_view.update_item_status(source, "Failed", STATUS_ERR)
                self.preview_view.canvas.set_caption("Export failed")
                if not self.is_auto_test:
                    QMessageBox.critical(self, "Export failed", f"Could not complete the export:\n\n{result.error_message}")
            if self.is_auto_test:
                QTimer.singleShot(600, self.close)

    # ------------------------------------------------------------------ batch export
    def _export_all_queue(self):
        if self._is_busy():
            return
        paths = self.queue_view.get_all_filepaths()
        if not paths:
            QMessageBox.information(self, "Queue empty", "Add images first.")
            return
        dest_dir = QFileDialog.getExistingDirectory(self, "Choose an Output Folder for the Queue", self.config.last_output_dir or "")
        if not dest_dir:
            return
        dest_dir = os.path.normpath(dest_dir)
        self.config.last_output_dir = dest_dir
        save_config(self.config)

        self._batch_queue = list(paths)
        self._batch_results = []
        self._batch_cancelled = False
        self._batch_dir = dest_dir
        for p in paths:
            self.queue_view.update_item_status(p, "Queued")
        self._process_next_batch_item()

    def _process_next_batch_item(self):
        if self._batch_cancelled:
            for p in self._batch_queue:
                self.queue_view.update_item_status(p, "Cancelled · not started", STATUS_WARN)
                self._batch_results.append((p, _failed(CANCELLED_MESSAGE)))
            self._batch_queue = []

        if not self._batch_queue:
            self._finish_batch()
            return

        filepath = self._batch_queue.pop(0)
        self._batch_current = filepath
        self.queue_view.update_item_status(filepath, "Processing…", STATUS_BUSY)
        try:
            target_w, target_h = self._target_dimensions_for(filepath)
            stem = os.path.splitext(os.path.basename(filepath))[0]
            out_path = generate_collision_safe_filename(self._batch_dir, stem, target_w, target_h,
                                                        self.controls_view.get_dpi(), self._output_extension(filepath))
        except Exception as e:
            self._on_batch_item_finished(_failed(f"Cannot read source: {e}"), started=False)
            return

        # Batch never replaces existing files: a "_N" suffix is used if the name is taken meanwhile
        params = self._build_job_params(filepath, out_path, overwrite=False)
        self._start_worker(params, "batch", self._on_batch_item_finished)

    def _on_batch_item_finished(self, res: JobExecutionResult, started: bool = True):
        if started:
            self._worker_done()
        filepath = self._batch_current
        self._batch_results.append((filepath, res))
        if res.success:
            self.queue_view.update_item_status(filepath, f"Done · {os.path.basename(res.output_path)}", STATUS_OK)
        elif res.error_message == CANCELLED_MESSAGE:
            self.queue_view.update_item_status(filepath, "Cancelled · nothing written", STATUS_WARN)
        else:
            self.queue_view.update_item_status(filepath, f"Failed · {res.error_message}", STATUS_ERR)
        self._process_next_batch_item()

    def _finish_batch(self):
        results = self._batch_results
        ok = sum(1 for _, r in results if r.success)
        cancelled = sum(1 for _, r in results if r.error_message == CANCELLED_MESSAGE)
        failed = len(results) - ok - cancelled
        self.status_bar_view.set_stage(f"Queue finished: {ok} exported, {failed} failed, {cancelled} cancelled.", error=failed > 0)
        if not self.is_auto_test and results:
            BatchSummaryDialog(results, self).exec()

    # ------------------------------------------------------------------ cancel / close
    def _cancel_processing(self):
        if self._active_kind == "batch":
            self._batch_cancelled = True
        if self._active_worker:
            self._active_worker.cancel()
            self.status_bar_view.set_stage("Cancelling… (stops at the next safe point)")

    def closeEvent(self, event):
        if self._active_worker is not None and self._active_worker.isRunning():
            if not self.is_auto_test:
                answer = QMessageBox.question(
                    self, "Job running",
                    "A job is still running. Cancel it and quit? No partial file will be kept.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if answer != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
            self._batch_cancelled = True
            self._active_worker.cancel()
            self._active_worker.wait(120000)
        if not self._closing_saved:
            self._closing_saved = True
            self._save_timer.stop()
            self.controls_view.collect_preferences(self.config)
            self._save_window_state()
            save_config(self.config)
        event.accept()

    # ------------------------------------------------------------------ help
    def _show_about_dialog(self):
        self._build_about_dialog().exec()

    def _build_about_dialog(self) -> QMessageBox:
        box = QMessageBox(self)
        box.setWindowTitle("About PrintScale Studio")
        # Transparent logo whose lettering contrasts with the current theme's dialog surface
        logo = render_logo(self.config.theme, 44, self.devicePixelRatioF())
        if not logo.isNull():
            box.setIconPixmap(logo)
        box.setText(
            f"<b>PrintScale Studio {__version__}</b><br>"
            "Raster image enlargement and print export for Windows.<br><br>"
            "Inference: ONNX Runtime (DirectML GPU and CPU)<br>"
            "Colour: sRGB output with an embedded ICC profile<br>"
            "Resolution: PNG pHYs and JPEG JFIF/EXIF metadata<br><br>"
            "Built with Python, PySide6/Qt 6, NumPy, Pillow and Real-ESRGAN models."
        )
        return box

    def _show_dpi_guide(self):
        QMessageBox.information(
            self, "Print DPI and Pixels",
            "<p><b>DPI is print-size information, not image detail.</b></p>"
            "<p><b>Print size:</b> the physical size stays fixed and DPI sets the pixels. "
            "14 × 16 in: 300 DPI = 4200 × 4800 px · 400 = 5600 × 6400 · 500 = 7000 × 8000 · 600 = 8400 × 9600.</p>"
            "<p><b>Pixel canvas:</b> the pixels stay fixed and DPI sets the print size "
            "(4200 × 4800 px at 500 DPI = 8.4 × 9.6 in).</p>"
            "<p><b>DPI metadata only:</b> only the stored resolution changes; pixels and format stay as they are.</p>"
        )

    def _show_upload_preset_guide(self):
        QMessageBox.information(
            self, "Upload Profile Limits",
            "<p>Format: PNG or JPEG · Maximum file size: 50 MB, defined as 52,428,800 bytes · "
            "Maximum 23,000 pixels on either axis · Recommended canvas 4200 × 4800 px.</p>"
            "<p>Each export is checked against these limits using the saved file. "
            "PrintScale Studio never changes size, format, alpha or quality to pass a limit.</p>"
        )
