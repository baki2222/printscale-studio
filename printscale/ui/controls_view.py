"""
PrintScale Studio - Settings panel
Processing, Output Size, Composition, Enhancement and Export, in one vertically scrolling
column. Rows that could exceed the panel width wrap (FlowLayout) or stack vertically, so the
panel never needs horizontal scrolling. Every control feeds the getters used to build
JobParameters; preferences are applied/collected explicitly (see apply_preferences).
"""

from typing import Optional, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QRadioButton, QButtonGroup,
    QLabel, QFrame, QSpinBox, QDoubleSpinBox, QSlider, QComboBox, QCheckBox, QScrollArea,
    QColorDialog, QSizePolicy
)
from PySide6.QtGui import QColor, QPixmap, QIcon, QPainter

from printscale.core.geometry import (
    DimensionMode, PhysicalUnit, CompositionMode, CropAlignment,
    calculate_target_pixels, calculate_physical_size, plan_canvas_sizing, estimate_job_memory_bytes
)
from printscale.core.metadata import ImageMetadataInfo
from printscale.core.enhancement import ProcessingMode
from printscale.core.config import UPLOAD_MAX_PIXELS_PER_AXIS, AppConfig
from printscale.ui.widgets import FlowLayout, CollapsibleSection, hline

PANEL_MIN_WIDTH = 286


def _label(text, name=None, wrap=False, parent=None):
    lbl = QLabel(text, parent)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    if wrap:
        lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lbl.setMinimumWidth(10)
    return lbl


class ControlsView(QWidget):
    parameters_changed = Signal()
    prefer_gpu_changed = Signal(bool)
    preferences_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_meta: Optional[ImageMetadataInfo] = None
        self._updating_fields = False
        self._applying_prefs = False
        self._current_bg_color = (255, 255, 255)
        self.setMinimumWidth(PANEL_MIN_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(self)
        frame.setObjectName("panel")
        outer.addWidget(frame)
        frame_lay = QVBoxLayout(frame)
        frame_lay.setContentsMargins(1, 1, 1, 1)

        self.scroll = QScrollArea(frame)
        self.scroll.setObjectName("settingsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Layout guarantees the content fits the width; never offer horizontal scrolling
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frame_lay.addWidget(self.scroll)

        container = QWidget(self.scroll)
        container.setObjectName("settingsContent")
        self.layout = QVBoxLayout(container)
        self.layout.setContentsMargins(14, 12, 14, 14)
        self.layout.setSpacing(10)

        self._build_mode_section()
        self.layout.addWidget(hline(container))
        self._build_sizing_section()
        self.layout.addWidget(hline(container))
        self._build_composition_section()
        self.layout.addWidget(hline(container))
        self._build_quality_section()
        self.layout.addWidget(hline(container))
        self._build_export_section()
        self.layout.addStretch()
        self.scroll.setWidget(container)

        # Initialize defaults, then make visibility match the selected modes
        self._apply_preset_pod()
        self._on_dim_mode_changed()
        self._on_mode_toggled()
        self._on_format_changed()
        self._on_composition_changed()

    # ------------------------------------------------------------------ section builders
    def _section(self, title: str) -> Tuple[QWidget, QVBoxLayout]:
        box = QWidget(self)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(_label(title, "sectionTitle", parent=box))
        self.layout.addWidget(box)
        return box, lay

    def _radio_with_hint(self, lay, text, hint, group):
        rb = QRadioButton(text, self)
        group.addButton(rb)
        lay.addWidget(rb)
        if hint:
            h = _label(hint, "hint", wrap=True, parent=self)
            h.setContentsMargins(24, 0, 0, 2)
            lay.addWidget(h)
        return rb

    def _build_mode_section(self):
        box, fl = self._section("Processing")
        self._mode_frame = box
        self.mode_group = QButtonGroup(box)
        self.rb_preserve = self._radio_with_hint(
            fl, "Preserve Artwork", "Faithful Lanczos resampling. Best for lettering, logos and textured designs.", self.mode_group)
        self.rb_illustration = self._radio_with_hint(
            fl, "AI Illustration", "Real-ESRGAN anime model. Sharper lines on clean flat-colour art.", self.mode_group)
        self.rb_photo = self._radio_with_hint(
            fl, "AI Photo", "Real-ESRGAN photo model for photographs and product shots.", self.mode_group)
        self.rb_preserve.setChecked(True)
        self.rb_preserve.setToolTip("Non-generative resampling: adds no invented detail.")
        self.rb_illustration.setToolTip("AI enlargement for illustrations. Can smooth fine texture.")
        self.rb_photo.setToolTip("AI enlargement for photographs. Can alter small lettering.")

        self.lbl_mode_note = _label(
            "AI modes can alter small lettering, flatten fine texture and darken faint edge fringes. "
            "Check the crop preview on light and dark backgrounds.", "note", wrap=True, parent=box)
        fl.addWidget(self.lbl_mode_note)

        self.adv_hardware = CollapsibleSection("Hardware", box)
        self.chk_gpu = QCheckBox("Use GPU (DirectML) when available", self.adv_hardware.body)
        self.chk_gpu.setToolTip("When off, AI modes run on the CPU. The device actually used is shown in the status bar and export summary.")
        self.chk_gpu.setChecked(True)
        self.adv_hardware.body_layout.addWidget(self.chk_gpu)
        self.adv_hardware.body_layout.addWidget(
            _label("Applies to AI modes. Preserve Artwork always runs on the CPU.", "hint", wrap=True, parent=box))
        fl.addWidget(self.adv_hardware)

        self.rb_preserve.toggled.connect(self._on_mode_toggled)
        self.rb_illustration.toggled.connect(self._on_mode_toggled)
        self.rb_photo.toggled.connect(self._on_mode_toggled)
        self.chk_gpu.toggled.connect(self._on_gpu_toggled)

    def _build_sizing_section(self):
        box, fl = self._section("Output Size")
        self._sizing_frame = box

        self.dim_mode_group = QButtonGroup(box)
        self.rb_dim_pixel = QRadioButton("Pixel canvas", box)
        self.rb_dim_pixel.setToolTip("Exact pixel size. Changing DPI changes only the reported print size.")
        self.rb_dim_print = QRadioButton("Print size", box)
        self.rb_dim_print.setToolTip("Physical size in inches or cm. Changing DPI changes the pixel size.")
        self.rb_dim_meta = QRadioButton("DPI metadata only", box)
        self.rb_dim_meta.setToolTip("Changes stored print resolution only. Pixels and format stay as in the source.")
        for rb in (self.rb_dim_pixel, self.rb_dim_print, self.rb_dim_meta):
            self.dim_mode_group.addButton(rb)
        self.rb_dim_pixel.setChecked(True)
        mode_flow = FlowLayout(None, 14, 4)
        for rb in (self.rb_dim_pixel, self.rb_dim_print, self.rb_dim_meta):
            mode_flow.addWidget(rb)
        fl.addLayout(mode_flow)

        # Presets
        preset_flow = FlowLayout(None, 6, 6)
        self.btn_preset_pod = QPushButton("4200 × 4800 px", box)
        self.btn_preset_pod.setToolTip("POD canvas preset: fixed 4200 × 4800 pixels at 300 DPI.")
        self.btn_preset_apparel = QPushButton("14 × 16 in", box)
        self.btn_preset_apparel.setToolTip("Apparel print preset: fixed 14 × 16 inches; pixels follow the DPI.")
        self.lbl_presets = _label("Presets", "muted", parent=box)
        self.lbl_presets.setMinimumHeight(self.btn_preset_pod.sizeHint().height())
        preset_flow.addWidget(self.lbl_presets)
        preset_flow.addWidget(self.btn_preset_pod)
        preset_flow.addWidget(self.btn_preset_apparel)
        fl.addLayout(preset_flow)

        # Pixel inputs
        self.pixel_size_widget = QWidget(box)
        pg = QGridLayout(self.pixel_size_widget)
        pg.setContentsMargins(0, 0, 0, 0)
        pg.setHorizontalSpacing(8)
        pg.setVerticalSpacing(6)
        self.spin_px_w = QSpinBox(self.pixel_size_widget)
        self.spin_px_h = QSpinBox(self.pixel_size_widget)
        for i, (lbl, spin) in enumerate((("Width", self.spin_px_w), ("Height", self.spin_px_h))):
            spin.setRange(16, 30000)
            spin.setSingleStep(100)
            spin.setSuffix(" px")
            spin.setAccelerated(True)
            spin.setAccessibleName(f"{lbl} in pixels")
            pg.addWidget(_label(lbl, parent=self.pixel_size_widget), i, 0)
            pg.addWidget(spin, i, 1)
        pg.setColumnStretch(1, 1)
        fl.addWidget(self.pixel_size_widget)

        # Physical inputs
        self.print_size_widget = QWidget(box)
        qg = QGridLayout(self.print_size_widget)
        qg.setContentsMargins(0, 0, 0, 0)
        qg.setHorizontalSpacing(8)
        qg.setVerticalSpacing(6)
        self.spin_print_w = QDoubleSpinBox(self.print_size_widget)
        self.spin_print_h = QDoubleSpinBox(self.print_size_widget)
        for i, (lbl, spin) in enumerate((("Width", self.spin_print_w), ("Height", self.spin_print_h))):
            spin.setRange(0.1, 500.0)
            spin.setDecimals(2)
            spin.setSingleStep(0.5)
            spin.setAccessibleName(f"Print {lbl.lower()}")
            qg.addWidget(_label(lbl, parent=self.print_size_widget), i, 0)
            qg.addWidget(spin, i, 1)
        self.combo_unit = QComboBox(self.print_size_widget)
        self.combo_unit.addItems(["in", "cm"])
        self.combo_unit.setToolTip("Unit for print width and height")
        self.combo_unit.setAccessibleName("Print size unit")
        qg.addWidget(_label("Unit", parent=self.print_size_widget), 2, 0)
        qg.addWidget(self.combo_unit, 2, 1)
        qg.setColumnStretch(1, 1)
        fl.addWidget(self.print_size_widget)

        self.chk_lock_aspect = QCheckBox("Lock aspect ratio to the source", box)
        self.chk_lock_aspect.setChecked(True)
        fl.addWidget(self.chk_lock_aspect)

        # DPI choices (wrap instead of cropping)
        fl.addWidget(_label("Print resolution (DPI)", "muted", parent=box))
        dpi_flow = FlowLayout(None, 6, 6)
        self.dpi_group = QButtonGroup(box)
        for dpi in (300, 400, 500, 600):
            b = QPushButton(str(dpi), box)
            b.setObjectName("segment")
            b.setCheckable(True)
            b.setMinimumWidth(56)
            b.setToolTip(f"{dpi} pixels per inch")
            b.setAccessibleName(f"{dpi} DPI")
            self.dpi_group.addButton(b, dpi)
            setattr(self, f"btn_dpi_{dpi}", b)
            dpi_flow.addWidget(b)
        self.btn_dpi_300.setChecked(True)
        fl.addLayout(dpi_flow)

        self.lbl_meta_note = _label(
            "Only the stored print resolution changes. Pixels, alpha, colours and file format (PNG or JPEG) "
            "stay exactly as in the source.", "note", wrap=True, parent=box)
        fl.addWidget(self.lbl_meta_note)

        # Output summary (always visible)
        card = QFrame(box)
        card.setObjectName("card")
        cl = QGridLayout(card)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setHorizontalSpacing(10)
        cl.setVerticalSpacing(3)
        self.lbl_target_info = _label("", "summaryValue", wrap=True, parent=card)
        self.lbl_phys_info = _label("", wrap=True, parent=card)
        self.lbl_scale_info = _label("", "muted", wrap=True, parent=card)
        self.lbl_resource_info = _label("", "muted", wrap=True, parent=card)
        self.lbl_upload_preset = _label("", "ok", wrap=True, parent=card)
        for r, (k, v) in enumerate((("Pixels", self.lbl_target_info), ("Print", self.lbl_phys_info),
                                    ("Scale", self.lbl_scale_info), ("Memory", self.lbl_resource_info),
                                    ("Upload", self.lbl_upload_preset))):
            key = _label(k, "faint", parent=card)
            cl.addWidget(key, r, 0, Qt.AlignmentFlag.AlignTop)
            cl.addWidget(v, r, 1)
        cl.setColumnStretch(1, 1)
        fl.addWidget(card)
        self.lbl_src_info = _label("Source: none", "muted", wrap=True, parent=box)
        fl.addWidget(self.lbl_src_info)

        # Advanced sizing
        self.adv_sizing = CollapsibleSection("Advanced size options", box)
        crow = QHBoxLayout()
        crow.addWidget(_label("Custom DPI", parent=self.adv_sizing.body))
        self.spin_custom_dpi = QSpinBox(self.adv_sizing.body)
        self.spin_custom_dpi.setRange(72, 1200)
        self.spin_custom_dpi.setValue(300)
        self.spin_custom_dpi.setAccessibleName("Custom DPI")
        crow.addWidget(self.spin_custom_dpi, 1)
        self.adv_sizing.body_layout.addLayout(crow)
        self.adv_sizing.body_layout.addWidget(_label("Pixel canvas from source size", "muted", parent=self.adv_sizing.body))
        mult_flow = FlowLayout(None, 6, 6)
        self.btn_mult_orig = QPushButton("1×", self.adv_sizing.body)
        self.btn_mult_2x = QPushButton("2×", self.adv_sizing.body)
        self.btn_mult_4x = QPushButton("4×", self.adv_sizing.body)
        for b, f in ((self.btn_mult_orig, 1), (self.btn_mult_2x, 2), (self.btn_mult_4x, 4)):
            b.setToolTip(f"Set the pixel canvas to {f}× the source dimensions")
            b.setMinimumWidth(48)
            mult_flow.addWidget(b)
        self.adv_sizing.body_layout.addLayout(mult_flow)
        fl.addWidget(self.adv_sizing)

        # Signals
        self.rb_dim_print.toggled.connect(self._on_dim_mode_changed)
        self.rb_dim_pixel.toggled.connect(self._on_dim_mode_changed)
        self.rb_dim_meta.toggled.connect(self._on_dim_mode_changed)
        self.btn_preset_pod.clicked.connect(self._apply_preset_pod)
        self.btn_preset_apparel.clicked.connect(self._apply_preset_apparel)
        self.btn_mult_orig.clicked.connect(lambda: self._apply_multiplier(1.0))
        self.btn_mult_2x.clicked.connect(lambda: self._apply_multiplier(2.0))
        self.btn_mult_4x.clicked.connect(lambda: self._apply_multiplier(4.0))
        self.spin_print_w.valueChanged.connect(self._on_print_w_changed)
        self.spin_print_h.valueChanged.connect(self._on_print_h_changed)
        self.combo_unit.currentIndexChanged.connect(self._on_unit_changed)
        self.spin_px_w.valueChanged.connect(self._on_px_w_changed)
        self.spin_px_h.valueChanged.connect(self._on_px_h_changed)
        self.dpi_group.idClicked.connect(self._on_dpi_btn_clicked)
        self.spin_custom_dpi.valueChanged.connect(self._on_custom_dpi_changed)
        self.chk_lock_aspect.toggled.connect(self._trigger_update)

    def _build_composition_section(self):
        box, fl = self._section("Composition")
        self._composition_frame = box
        self.combo_composition = QComboBox(box)
        self.combo_composition.addItem("Fit with padding", CompositionMode.FIT_PAD)
        self.combo_composition.addItem("Crop to fill", CompositionMode.CROP)
        self.combo_composition.setToolTip("Fit keeps the whole image and pads the rest of the canvas. "
                                          "Crop fills the canvas and trims the overflow.")
        self.combo_composition.setAccessibleName("Composition")
        fl.addWidget(self.combo_composition)
        self.lbl_comp_hint = _label("", "hint", wrap=True, parent=box)
        fl.addWidget(self.lbl_comp_hint)
        self.crop_row = QWidget(box)
        cr = QHBoxLayout(self.crop_row)
        cr.setContentsMargins(0, 0, 0, 0)
        cr.addWidget(_label("Keep", parent=self.crop_row))
        self.combo_crop_align = QComboBox(self.crop_row)
        for text, val in (("Center", CropAlignment.CENTER), ("Top", CropAlignment.TOP), ("Bottom", CropAlignment.BOTTOM),
                          ("Left", CropAlignment.LEFT), ("Right", CropAlignment.RIGHT)):
            self.combo_crop_align.addItem(text, val)
        self.combo_crop_align.setAccessibleName("Crop alignment")
        cr.addWidget(self.combo_crop_align, 1)
        fl.addWidget(self.crop_row)
        self.combo_composition.currentIndexChanged.connect(self._on_composition_changed)
        self.combo_crop_align.currentIndexChanged.connect(self._on_composition_changed)

    def _build_quality_section(self):
        box, fl = self._section("Enhancement")
        self._quality_frame = box
        row = QHBoxLayout()
        row.addWidget(_label("Sharpening", parent=box))
        row.addStretch()
        self.lbl_sharp_val = _label("Off", "summaryValue", parent=box)
        row.addWidget(self.lbl_sharp_val)
        fl.addLayout(row)
        self.slider_sharpen = QSlider(Qt.Orientation.Horizontal, box)
        self.slider_sharpen.setRange(0, 100)
        self.slider_sharpen.setValue(0)
        self.slider_sharpen.setAccessibleName("Sharpening amount")
        self.slider_sharpen.setToolTip("Unsharp mask after resizing. 0 = off, recommended for lettering.")
        fl.addWidget(self.slider_sharpen)
        fl.addWidget(_label("Off keeps edges exactly as resampled. Higher values can create light halos.",
                            "hint", wrap=True, parent=box))
        self.slider_sharpen.valueChanged.connect(self._on_sharpen_changed)

    def _build_export_section(self):
        box, fl = self._section("Export")
        self._export_frame = box
        fmt_flow = FlowLayout(None, 14, 4)
        self.fmt_group = QButtonGroup(box)
        self.rb_png = QRadioButton("PNG", box)
        self.rb_png.setToolTip("Lossless, keeps transparency")
        self.rb_jpg = QRadioButton("JPEG", box)
        self.rb_jpg.setToolTip("Lossy, no transparency: transparent areas are flattened onto the background colour")
        self.fmt_group.addButton(self.rb_png)
        self.fmt_group.addButton(self.rb_jpg)
        self.rb_png.setChecked(True)
        fmt_flow.addWidget(self.rb_png)
        fmt_flow.addWidget(self.rb_jpg)
        fl.addLayout(fmt_flow)
        self.lbl_fmt_hint = _label("Lossless; transparency is kept.", "hint", wrap=True, parent=box)
        fl.addWidget(self.lbl_fmt_hint)

        self.jpeg_options_widget = QWidget(box)
        jl = QVBoxLayout(self.jpeg_options_widget)
        jl.setContentsMargins(0, 0, 0, 0)
        jl.setSpacing(6)
        qrow = QHBoxLayout()
        qrow.addWidget(_label("Quality", parent=self.jpeg_options_widget))
        qrow.addStretch()
        self.lbl_jpeg_q_val = _label("95", "summaryValue", parent=self.jpeg_options_widget)
        qrow.addWidget(self.lbl_jpeg_q_val)
        jl.addLayout(qrow)
        self.slider_jpeg_q = QSlider(Qt.Orientation.Horizontal, self.jpeg_options_widget)
        self.slider_jpeg_q.setRange(70, 100)
        self.slider_jpeg_q.setValue(95)
        self.slider_jpeg_q.setAccessibleName("JPEG quality")
        jl.addWidget(self.slider_jpeg_q)
        brow = QHBoxLayout()
        brow.addWidget(_label("Background", parent=self.jpeg_options_widget))
        self.btn_bg_color = QPushButton("#FFFFFF", self.jpeg_options_widget)
        self.btn_bg_color.setToolTip("Colour used behind transparent areas in JPEG output")
        self.btn_bg_color.setAccessibleName("JPEG background colour")
        brow.addWidget(self.btn_bg_color, 1)
        jl.addLayout(brow)
        fl.addWidget(self.jpeg_options_widget)

        self.rb_png.toggled.connect(self._on_format_changed)
        self.slider_jpeg_q.valueChanged.connect(self._on_jpeg_quality_changed)
        self.btn_bg_color.clicked.connect(self._pick_bg_color)
        self._update_bg_button()

    # ------------------------------------------------------------------ preferences (U-5)
    def apply_preferences(self, cfg: AppConfig):
        """Shows validated saved preferences in the controls without emitting saves for each step."""
        self._applying_prefs = True
        self._updating_fields = True
        try:
            {"preserve_artwork": self.rb_preserve, "ai_illustration": self.rb_illustration,
             "ai_photo": self.rb_photo}[cfg.default_processing_mode].setChecked(True)
            (self.rb_jpg if cfg.default_format == "JPEG" else self.rb_png).setChecked(True)
            self.slider_sharpen.setValue(cfg.sharpen_percent)
            self.slider_jpeg_q.setValue(cfg.jpeg_quality)
            self._current_bg_color = tuple(cfg.jpeg_bg_color)
            self._update_bg_button()
            self.combo_composition.setCurrentIndex(0 if cfg.default_composition_mode == "fit_pad" else 1)
            idx = self.combo_crop_align.findData(cfg.crop_alignment)
            self.combo_crop_align.setCurrentIndex(max(0, idx))
            self.chk_lock_aspect.setChecked(cfg.lock_aspect)
            self.combo_unit.setCurrentText(cfg.print_unit)
            self.spin_px_w.setValue(cfg.pixel_width)
            self.spin_px_h.setValue(cfg.pixel_height)
            self.spin_print_w.setValue(cfg.print_width)
            self.spin_print_h.setValue(cfg.print_height)
            (self.rb_dim_print if cfg.dimension_mode == "print_size" else self.rb_dim_pixel).setChecked(True)
            self.spin_custom_dpi.setValue(cfg.default_dpi)
            self._sync_dpi_buttons(cfg.default_dpi)
            self.set_prefer_gpu(cfg.prefer_gpu)
        finally:
            self._updating_fields = False
        try:
            self._on_dim_mode_changed()
            self._on_mode_toggled()
            self._on_format_changed()
            self._on_composition_changed()
            self._on_sharpen_changed(self.slider_sharpen.value())
            self.lbl_jpeg_q_val.setText(str(self.slider_jpeg_q.value()))
            self._refresh_calculations()
        finally:
            self._applying_prefs = False

    def collect_preferences(self, cfg: AppConfig):
        """Writes the current control values into cfg (metadata-only is never persisted)."""
        cfg.default_processing_mode = self.get_processing_mode().value
        cfg.default_format = self.get_output_format()
        cfg.sharpen_percent = self.slider_sharpen.value()
        cfg.jpeg_quality = self.slider_jpeg_q.value()
        cfg.jpeg_bg_color = list(self._current_bg_color)
        cfg.default_dpi = self.spin_custom_dpi.value()
        cfg.default_composition_mode = self.get_composition_mode().value
        cfg.crop_alignment = self.get_crop_alignment().value
        cfg.lock_aspect = self.chk_lock_aspect.isChecked()
        cfg.print_unit = self.combo_unit.currentText()
        cfg.pixel_width = self.spin_px_w.value()
        cfg.pixel_height = self.spin_px_h.value()
        cfg.print_width = round(self.spin_print_w.value(), 2)
        cfg.print_height = round(self.spin_print_h.value(), 2)
        if self.rb_dim_print.isChecked():
            cfg.dimension_mode = "print_size"
        elif self.rb_dim_pixel.isChecked():
            cfg.dimension_mode = "pixel_dims"
        cfg.prefer_gpu = self.chk_gpu.isChecked()

    # ------------------------------------------------------------------ handlers
    def set_metadata(self, meta: Optional[ImageMetadataInfo]):
        self._current_meta = meta
        if meta is None:
            self.lbl_src_info.setText("Source: none")
        else:
            alpha_str = "transparent" if meta.has_alpha else "opaque"
            self.lbl_src_info.setText(f"Source: {meta.width} × {meta.height} px, {meta.dpi_display}, {alpha_str}")
        self._refresh_calculations()

    def _on_mode_toggled(self):
        self.lbl_mode_note.setVisible(not self.rb_preserve.isChecked())
        self._refresh_calculations()
        self._trigger_update()

    def _on_gpu_toggled(self, on: bool):
        if not self._applying_prefs:
            self.prefer_gpu_changed.emit(on)
        self._trigger_update()

    def _on_composition_changed(self):
        is_crop = self.get_composition_mode() == CompositionMode.CROP
        self.crop_row.setVisible(is_crop)
        self.lbl_comp_hint.setText("Fills the canvas; the overflow is trimmed." if is_crop else
                                   "Keeps the whole image; the remaining canvas is padded "
                                   "(transparent for PNG, background colour for JPEG).")
        self._refresh_calculations()
        self._trigger_update()

    def _on_dim_mode_changed(self):
        is_print = self.rb_dim_print.isChecked()
        is_pixel = self.rb_dim_pixel.isChecked()
        is_meta = self.rb_dim_meta.isChecked()
        self.print_size_widget.setVisible(is_print)
        self.pixel_size_widget.setVisible(is_pixel)
        self.chk_lock_aspect.setVisible(not is_meta)
        self.lbl_presets.setVisible(not is_meta)
        self.btn_preset_pod.setVisible(not is_meta)
        self.btn_preset_apparel.setVisible(not is_meta)
        # Metadata-only never resamples or re-encodes, so processing/composition/format do not apply
        for frame in (self._mode_frame, self._composition_frame, self._quality_frame, self._export_frame):
            frame.setEnabled(not is_meta)
        self.lbl_meta_note.setVisible(is_meta)
        for btn in (self.btn_mult_orig, self.btn_mult_2x, self.btn_mult_4x):
            btn.setEnabled(not is_meta)
        self._refresh_calculations()
        self._trigger_update()

    def _apply_preset_pod(self):
        """Preset: POD canvas: 4200 x 4800 px (fixed pixel mode)."""
        self._updating_fields = True
        self.rb_dim_pixel.setChecked(True)
        self.spin_px_w.setValue(4200)
        self.spin_px_h.setValue(4800)
        self.spin_custom_dpi.setValue(300)
        self._sync_dpi_buttons(300)
        self._updating_fields = False
        self._refresh_calculations()
        self._trigger_update()

    def _apply_preset_apparel(self):
        """Preset: Apparel print: 14 x 16 in (fixed physical mode)."""
        self._updating_fields = True
        self.rb_dim_print.setChecked(True)
        self.combo_unit.setCurrentText("in")
        self.spin_print_w.setValue(14.0)
        self.spin_print_h.setValue(16.0)
        self.spin_custom_dpi.setValue(300)
        self._sync_dpi_buttons(300)
        self._updating_fields = False
        self._refresh_calculations()
        self._trigger_update()

    def _apply_multiplier(self, factor: float):
        if not self._current_meta:
            return
        self._updating_fields = True
        self.rb_dim_pixel.setChecked(True)
        self.spin_px_w.setValue(int(round(self._current_meta.width * factor)))
        self.spin_px_h.setValue(int(round(self._current_meta.height * factor)))
        self._updating_fields = False
        self._refresh_calculations()
        self._trigger_update()

    def _on_print_w_changed(self, val: float):
        if not self._updating_fields and self.chk_lock_aspect.isChecked() and self._current_meta:
            self._updating_fields = True
            self.spin_print_h.setValue(round(val * self._current_meta.height / self._current_meta.width, 2))
            self._updating_fields = False
        self._refresh_calculations()
        self._trigger_update()

    def _on_print_h_changed(self, val: float):
        if not self._updating_fields and self.chk_lock_aspect.isChecked() and self._current_meta:
            self._updating_fields = True
            self.spin_print_w.setValue(round(val * self._current_meta.width / self._current_meta.height, 2))
            self._updating_fields = False
        self._refresh_calculations()
        self._trigger_update()

    def _on_unit_changed(self):
        self._refresh_calculations()
        self._trigger_update()

    def _on_px_w_changed(self, val: int):
        if not self._updating_fields and self.chk_lock_aspect.isChecked() and self._current_meta:
            self._updating_fields = True
            self.spin_px_h.setValue(max(1, int(round(val * self._current_meta.height / self._current_meta.width))))
            self._updating_fields = False
        self._refresh_calculations()
        self._trigger_update()

    def _on_px_h_changed(self, val: int):
        if not self._updating_fields and self.chk_lock_aspect.isChecked() and self._current_meta:
            self._updating_fields = True
            self.spin_px_w.setValue(max(1, int(round(val * self._current_meta.width / self._current_meta.height))))
            self._updating_fields = False
        self._refresh_calculations()
        self._trigger_update()

    def _sync_dpi_buttons(self, dpi: int):
        btn = self.dpi_group.button(dpi)
        if btn:
            btn.setChecked(True)
        else:
            self.dpi_group.setExclusive(False)
            for b in self.dpi_group.buttons():
                b.setChecked(False)
            self.dpi_group.setExclusive(True)

    def _on_dpi_btn_clicked(self, dpi: int):
        self._updating_fields = True
        self.spin_custom_dpi.setValue(dpi)
        self._updating_fields = False
        self._refresh_calculations()
        self._trigger_update()

    def _on_custom_dpi_changed(self, dpi: int):
        if self._updating_fields:
            return
        self._sync_dpi_buttons(dpi)
        self._refresh_calculations()
        self._trigger_update()

    def _on_sharpen_changed(self, val: int):
        self.lbl_sharp_val.setText("Off" if val == 0 else f"{val}%")
        self._trigger_update()

    def _on_jpeg_quality_changed(self, val: int):
        self.lbl_jpeg_q_val.setText(str(val))
        self._trigger_update()

    def _on_format_changed(self):
        is_jpg = self.rb_jpg.isChecked()
        self.jpeg_options_widget.setVisible(is_jpg)
        self.lbl_fmt_hint.setText("Lossy; no transparency. Transparent areas are flattened onto the background colour."
                                  if is_jpg else "Lossless; transparency is kept.")
        self._trigger_update()

    def _update_bg_button(self):
        r, g, b = self._current_bg_color
        self.btn_bg_color.setText(f"#{r:02X}{g:02X}{b:02X}")
        pm = QPixmap(14, 14)
        pm.fill(QColor(r, g, b))
        painter = QPainter(pm)
        painter.setPen(QColor(128, 128, 128))
        painter.drawRect(0, 0, 13, 13)
        painter.end()
        self.btn_bg_color.setIcon(QIcon(pm))

    def _pick_bg_color(self):
        col = QColorDialog.getColor(QColor(*self._current_bg_color), self, "Background colour for JPEG flattening")
        if col.isValid():
            self._current_bg_color = (col.red(), col.green(), col.blue())
            self._update_bg_button()
            self._trigger_update()

    def _refresh_calculations(self):
        dpi = self.spin_custom_dpi.value()
        meta = self._current_meta
        if self.rb_dim_print.isChecked():
            target_w, target_h = calculate_target_pixels(self.spin_print_w.value(), self.spin_print_h.value(), dpi, self.get_print_unit())
        elif self.rb_dim_pixel.isChecked():
            target_w, target_h = self.spin_px_w.value(), self.spin_px_h.value()
        else:
            target_w = meta.width if meta else 0
            target_h = meta.height if meta else 0
        phys_w_in, phys_h_in = calculate_physical_size(target_w, target_h, dpi, PhysicalUnit.INCHES)
        self.lbl_target_info.setText(f"{target_w:,} × {target_h:,} px" if target_w else "Same as source")
        self.lbl_phys_info.setText(f"{phys_w_in:.2f} × {phys_h_in:.2f} in ({phys_w_in * 2.54:.2f} × {phys_h_in * 2.54:.2f} cm) at {dpi} DPI"
                                   if target_w else f"Source pixels at {dpi} DPI")
        if meta and meta.width > 0 and target_w and not self.rb_dim_meta.isChecked():
            plan = plan_canvas_sizing(meta.width, meta.height, target_w, target_h, self.get_composition_mode(), self.get_crop_alignment())
            scale = plan.scaled_content_w / meta.width
            self.lbl_scale_info.setText(f"{scale:.2f}× from {meta.width} × {meta.height} px")
            uses_model = self.get_processing_mode() != ProcessingMode.PRESERVE_ARTWORK and scale > 1.0
            gb = estimate_job_memory_bytes(meta.width, meta.height, plan, uses_model) / 2**30
            self.lbl_resource_info.setText(f"≈ {gb:.1f} GB working memory")
        elif self.rb_dim_meta.isChecked():
            self.lbl_scale_info.setText("No resampling")
            self.lbl_resource_info.setText("Minimal")
        else:
            self.lbl_scale_info.setText("Import an image to see the scale")
            self.lbl_resource_info.setText("–")
        mp = target_w * target_h / 1e6
        if max(target_w, target_h) > UPLOAD_MAX_PIXELS_PER_AXIS:
            name, text = "error", f"Exceeds {UPLOAD_MAX_PIXELS_PER_AXIS:,} px per axis"
        elif mp > 65:
            name, text = "warn", "Dimensions OK; a canvas this large may exceed 50 MB. The saved file is checked after export."
        else:
            name, text = "ok", "Dimensions OK. File size is checked on the saved file."
        self.lbl_upload_preset.setText(text)
        if self.lbl_upload_preset.objectName() != name:
            self.lbl_upload_preset.setObjectName(name)
            self.lbl_upload_preset.style().unpolish(self.lbl_upload_preset)
            self.lbl_upload_preset.style().polish(self.lbl_upload_preset)

    def _trigger_update(self):
        self.parameters_changed.emit()
        if not self._applying_prefs:
            self.preferences_changed.emit()

    # ------------------------------------------------------------------ getters
    def get_dimension_mode(self) -> DimensionMode:
        if self.rb_dim_print.isChecked():
            return DimensionMode.PRINT_SIZE
        elif self.rb_dim_pixel.isChecked():
            return DimensionMode.PIXEL_DIMS
        return DimensionMode.METADATA_ONLY

    def get_processing_mode(self) -> ProcessingMode:
        if self.rb_preserve.isChecked():
            return ProcessingMode.PRESERVE_ARTWORK
        elif self.rb_illustration.isChecked():
            return ProcessingMode.AI_ILLUSTRATION
        return ProcessingMode.AI_PHOTO

    def get_target_dimensions(self) -> Tuple[int, int]:
        mode = self.get_dimension_mode()
        dpi = self.spin_custom_dpi.value()
        if mode == DimensionMode.PRINT_SIZE:
            return calculate_target_pixels(self.spin_print_w.value(), self.spin_print_h.value(), dpi, self.get_print_unit())
        elif mode == DimensionMode.PIXEL_DIMS:
            return self.spin_px_w.value(), self.spin_px_h.value()
        if self._current_meta:
            return self._current_meta.width, self._current_meta.height
        return 1000, 1000

    def get_print_unit(self) -> PhysicalUnit:
        return PhysicalUnit.INCHES if self.combo_unit.currentText() == "in" else PhysicalUnit.CENTIMETERS

    def set_prefer_gpu(self, prefer: bool):
        self.chk_gpu.blockSignals(True)
        self.chk_gpu.setChecked(prefer)
        self.chk_gpu.blockSignals(False)

    def set_hardware_toggle_enabled(self, enabled: bool):
        self.chk_gpu.setEnabled(enabled)

    def get_dpi(self) -> int:
        return self.spin_custom_dpi.value()

    def get_composition_mode(self) -> CompositionMode:
        # Qt hands str-enum item data back as plain str; normalise to the enum
        return CompositionMode(self.combo_composition.currentData())

    def get_crop_alignment(self) -> CropAlignment:
        return CropAlignment(self.combo_crop_align.currentData())

    def get_sharpen_percent(self) -> int:
        return self.slider_sharpen.value()

    def get_output_format(self) -> str:
        return "PNG" if self.rb_png.isChecked() else "JPEG"

    def get_jpeg_quality(self) -> int:
        return self.slider_jpeg_q.value()

    def get_jpeg_bg_color(self) -> Tuple[int, int, int]:
        return self._current_bg_color

    def set_section_icons(self, collapsed_icon, expanded_icon):
        for sec in (self.adv_hardware, self.adv_sizing):
            sec.set_icons(collapsed_icon, expanded_icon)
