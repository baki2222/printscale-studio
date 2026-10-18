"""
PrintScale Studio - Comparison viewer
- Split slider and side-by-side comparison with one shared zoom/pan transform.
- Fit / 100% / 200% expressed in real output pixels (honest when the display is downsampled).
- Checkerboard / white / black / grey backgrounds (viewer only; never written to exports).
- Toolbar built on QToolBar so actions that do not fit move into its overflow menu.
- Explicit empty, loading, preview and result captions.
"""

from typing import Optional, Tuple
from PIL import Image

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QFrame, QToolBar, QSizePolicy, QToolButton
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QImage, QFont, QWheelEvent, QMouseEvent, QPaintEvent,
    QAction, QActionGroup, QFontMetrics
)


def pil_to_qimage(pil_img: Image.Image) -> QImage:
    """Converts a PIL Image to a detached QImage."""
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888)
    return qimg.copy()


class ViewportCanvas(QWidget):
    zoom_changed = Signal(float, bool)
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(200, 160)
        self.setAccessibleName("Image comparison viewer")
        self.setAcceptDrops(True)

        self._original_pixmap: Optional[QPixmap] = None
        self._processed_pixmap: Optional[QPixmap] = None
        self._view_mode = "split"
        self._split_ratio = 0.5
        self._bg_mode = "checkerboard"
        self._zoom = 1.0
        self._is_fit_to_view = True
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._dragging_split = False
        self._dragging_pan = False
        self._last_mouse_pos = QPointF()
        self._output_size: Optional[Tuple[int, int]] = None
        self._display_scale = 1.0
        self._caption = ""
        self._labels = ("ORIGINAL", "RESULT")
        self._message: Optional[Tuple[str, str]] = ("No image loaded", "Drop images here, or use File › Add Images (Ctrl+O).")
        self._colors = {"viewer": QColor(16, 17, 20), "text": QColor(231, 232, 237), "muted": QColor(154, 157, 171),
                        "accent": QColor(99, 102, 241), "chip": QColor(22, 23, 27, 220)}
        self._checkerboard_tile = self._create_checker_pattern(12)

    def set_theme(self, palette: dict):
        self._colors = {"viewer": QColor(palette["viewer"]), "text": QColor(palette["text"]),
                        "muted": QColor(palette["muted"]), "accent": QColor(palette["accent"]),
                        "chip": QColor(palette["surface"]).darker(102)}
        self._colors["chip"].setAlpha(225)
        self.update()

    def _create_checker_pattern(self, size: int) -> QPixmap:
        pm = QPixmap(size * 2, size * 2)
        p = QPainter(pm)
        p.fillRect(0, 0, size * 2, size * 2, QColor(240, 240, 244))
        p.fillRect(size, 0, size, size, QColor(208, 209, 216))
        p.fillRect(0, size, size, size, QColor(208, 209, 216))
        p.end()
        return pm

    # ------------------------------------------------------------------ content
    def set_images(self, orig_pil: Optional[Image.Image], proc_pil: Optional[Image.Image],
                   output_size: Optional[Tuple[int, int]] = None, display_scale: float = 1.0):
        self._display_scale = display_scale
        ref = proc_pil if proc_pil is not None else orig_pil
        self._output_size = output_size or (ref.size if ref is not None else None)
        self._original_pixmap = QPixmap.fromImage(pil_to_qimage(orig_pil)) if orig_pil is not None else None
        self._processed_pixmap = QPixmap.fromImage(pil_to_qimage(proc_pil)) if proc_pil is not None else None
        if ref is None:
            self._message = ("No image loaded", "Drop images here, or use File › Add Images (Ctrl+O).")
        else:
            self._message = None
        self.zoom_to_fit()
        self.update()

    def set_caption(self, caption: str, labels: Optional[Tuple[str, str]] = None):
        """Caption chip text; pane labels change only when given, so a cancelled or failed job
        never relabels the images that are still on screen."""
        self._caption = caption
        if labels is not None:
            self._labels = labels
        self.update()

    def set_message(self, title: Optional[str], subtitle: str = ""):
        """Overlay message for loading/processing states (None clears it)."""
        self._message = (title, subtitle) if title else None
        self.update()

    def has_image(self) -> bool:
        return (self._processed_pixmap or self._original_pixmap) is not None

    def viewport_center_in_image(self) -> Optional[Tuple[float, float]]:
        """Image coordinates (fraction 0..1 of the displayed image) at the centre of the view."""
        pm = self._processed_pixmap or self._original_pixmap
        if pm is None or pm.isNull():
            return None
        cx = (self.width() / 2.0 - self._pan_x) / (pm.width() * self._zoom)
        cy = (self.height() / 2.0 - self._pan_y) / (pm.height() * self._zoom)
        return min(1.0, max(0.0, cx)), min(1.0, max(0.0, cy))

    def set_view_mode(self, mode: str):
        self._view_mode = mode
        self.update()

    def set_bg_mode(self, mode: str):
        self._bg_mode = mode
        self.update()

    # ------------------------------------------------------------------ zoom/pan
    def zoom_to_fit(self):
        self._is_fit_to_view = True
        pm = self._processed_pixmap or self._original_pixmap
        if pm and not pm.isNull() and self.width() > 0 and self.height() > 0:
            avail_w = self.width() - 32
            if self._view_mode == "side_by_side" and self._processed_pixmap and self._original_pixmap:
                avail_w = self.width() / 2.0 - 24
            scale_w = avail_w / pm.width()
            scale_h = (self.height() - 56) / pm.height()
            self._zoom = max(0.01, min(scale_w, scale_h))
            self._pan_x = (self.width() - pm.width() * self._zoom) / 2.0
            self._pan_y = (self.height() - pm.height() * self._zoom) / 2.0
        else:
            self._zoom, self._pan_x, self._pan_y = 1.0, 0.0, 0.0
        self.zoom_changed.emit(self._zoom, self._is_fit_to_view)
        self.update()

    def set_zoom_level(self, zoom: float):
        self._is_fit_to_view = False
        old_zoom = self._zoom
        self._zoom = max(0.02, min(16.0, zoom))
        cx, cy = self.width() / 2.0, self.height() / 2.0
        self._pan_x = cx - (cx - self._pan_x) * (self._zoom / old_zoom)
        self._pan_y = cy - (cy - self._pan_y) * (self._zoom / old_zoom)
        self.zoom_changed.emit(self._zoom, self._is_fit_to_view)
        self.update()

    def set_output_zoom(self, output_zoom: float):
        """Zoom expressed in real output pixels (1.0 = one output pixel per screen pixel)."""
        dpr = self.devicePixelRatioF() or 1.0
        self.set_zoom_level(output_zoom / max(self._display_scale, 1e-6) / dpr)

    def output_zoom(self) -> float:
        return self._zoom * self._display_scale * (self.devicePixelRatioF() or 1.0)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        new_zoom = max(0.02, min(16.0, self._zoom * factor))
        pos = event.position()
        self._is_fit_to_view = False
        self._pan_x = pos.x() - (pos.x() - self._pan_x) * (new_zoom / self._zoom)
        self._pan_y = pos.y() - (pos.y() - self._pan_y) * (new_zoom / self._zoom)
        self._zoom = new_zoom
        self.zoom_changed.emit(self._zoom, self._is_fit_to_view)
        self.update()

    def keyPressEvent(self, event):
        step = 40
        moves = {Qt.Key.Key_Left: (step, 0), Qt.Key.Key_Right: (-step, 0), Qt.Key.Key_Up: (0, step), Qt.Key.Key_Down: (0, -step)}
        if event.key() in moves:
            dx, dy = moves[event.key()]
            self._pan_x += dx
            self._pan_y += dy
            self._is_fit_to_view = False
            self.update()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._view_mode == "split" and self._original_pixmap and self._processed_pixmap:
                if abs(event.position().x() - self.width() * self._split_ratio) < 14:
                    self._dragging_split = True
                    self.setCursor(Qt.CursorShape.SplitHCursor)
                    return
            self._dragging_pan = True
            self._last_mouse_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._dragging_pan = True
            self._last_mouse_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging_split:
            self._split_ratio = max(0.02, min(0.98, event.position().x() / max(1.0, float(self.width()))))
            self.update()
            return
        if self._dragging_pan:
            diff = event.position() - self._last_mouse_pos
            self._pan_x += diff.x()
            self._pan_y += diff.y()
            self._last_mouse_pos = event.position()
            self._is_fit_to_view = False
            self.update()
            return
        if self._view_mode == "split" and self._original_pixmap and self._processed_pixmap and \
                abs(event.position().x() - self.width() * self._split_ratio) < 14:
            self.setCursor(Qt.CursorShape.SplitHCursor)
        elif self.has_image():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging_split = False
        self._dragging_pan = False
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.has_image() else Qt.CursorShape.ArrowCursor)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        import os
        paths = [u.toLocalFile() for u in event.mimeData().urls() if os.path.isfile(u.toLocalFile())]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()

    def mouseDoubleClickEvent(self, event):
        self.zoom_to_fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._is_fit_to_view:
            self.zoom_to_fit()

    # ------------------------------------------------------------------ painting
    def _draw_visible(self, painter: QPainter, target: QRectF, pm: QPixmap, clip: QRectF):
        """Draws only the part of `pm` that lands inside `clip`. Passing Qt the full, mostly off-screen
        target rect at fractional device pixel ratios (e.g. 150%) can make the raster engine drop the
        whole draw, which left one side-by-side pane blank at 100% zoom."""
        vis = target.intersected(clip).intersected(QRectF(self.rect()))
        if vis.isEmpty() or target.width() <= 0 or target.height() <= 0:
            return
        sx = pm.width() / target.width()
        sy = pm.height() / target.height()
        src = QRectF((vis.x() - target.x()) * sx, (vis.y() - target.y()) * sy, vis.width() * sx, vis.height() * sy)
        painter.drawPixmap(vis, pm, src)

    def _paint_background(self, painter, rect: QRectF):
        painter.save()
        # Intersect (not replace) so a pane's background never paints over the other pane
        painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
        if self._bg_mode == "checkerboard":
            painter.drawTiledPixmap(rect, self._checkerboard_tile, QPointF(rect.x(), rect.y()))
        else:
            painter.fillRect(rect, {"white": QColor(255, 255, 255), "black": QColor(0, 0, 0),
                                    "gray": QColor(128, 128, 128)}[self._bg_mode])
        painter.restore()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._colors["viewer"])
        ref_pm = self._processed_pixmap or self._original_pixmap
        if ref_pm is None or ref_pm.isNull():
            self._paint_message(painter)
            return
        # Smooth only when reducing; at 100% and above show exact pixels for inspection
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.output_zoom() < 0.999)

        dest_w = ref_pm.width() * self._zoom
        dest_h = ref_pm.height() * self._zoom
        both = self._original_pixmap is not None and self._processed_pixmap is not None

        if self._view_mode == "side_by_side" and both:
            half_w = self.width() / 2.0
            for idx, (pm, x_off, clip) in enumerate((
                    (self._original_pixmap, -half_w / 2.0, QRectF(0, 0, half_w - 1, self.height())),
                    (self._processed_pixmap, half_w / 2.0, QRectF(half_w + 1, 0, half_w - 1, self.height())))):
                rect = QRectF(self._pan_x + x_off, self._pan_y, dest_w, dest_h)
                painter.save()
                painter.setClipRect(clip)
                self._paint_background(painter, rect)
                self._draw_visible(painter, rect, pm, clip)
                painter.restore()
            painter.fillRect(QRectF(half_w - 1, 0, 2, self.height()), self._colors["accent"])
            self._draw_chip(painter, 12, 12, self._labels[0])
            self._draw_chip(painter, half_w + 12, 12, self._labels[1])
        else:
            rect = QRectF(self._pan_x, self._pan_y, dest_w, dest_h)
            self._paint_background(painter, rect)
            if self._view_mode == "split" and both:
                split_x = self.width() * self._split_ratio
                left_clip = QRectF(0, 0, split_x, self.height())
                right_clip = QRectF(split_x, 0, self.width() - split_x, self.height())
                painter.save()
                painter.setClipRect(left_clip)
                self._draw_visible(painter, rect, self._original_pixmap, left_clip)
                painter.restore()
                painter.save()
                painter.setClipRect(right_clip)
                self._draw_visible(painter, rect, self._processed_pixmap, right_clip)
                painter.restore()
                self._draw_split_handle(painter, split_x)
            else:
                self._draw_visible(painter, rect, ref_pm, QRectF(self.rect()))
        if self._caption:
            fm = QFontMetrics(self.font())
            # Comparison labels occupy the top row, so the caption goes just below them
            y = 12 if not both else 12 + fm.height() + 14
            self._draw_chip(painter, 12, y, self._caption)
        self._draw_hud(painter, ref_pm)
        if self._message:
            self._paint_message(painter, dim=True)

    def _draw_chip(self, painter, x, y, text):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = QFont(self.font())
        f.setBold(True)
        painter.setFont(f)
        fm = QFontMetrics(f)
        max_w = max(60, self.width() - x - 12)
        text = fm.elidedText(text, Qt.TextElideMode.ElideMiddle, int(max_w - 16))
        r = QRectF(x, y, fm.horizontalAdvance(text) + 16, fm.height() + 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._colors["chip"])
        painter.drawRoundedRect(r, 5, 5)
        painter.setPen(self._colors["text"])
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def _draw_split_handle(self, painter: QPainter, split_x: float):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(self._colors["accent"], 2))
        painter.drawLine(QPointF(split_x, 0), QPointF(split_x, self.height()))
        mid_y = self.height() / 2.0
        painter.setBrush(QBrush(self._colors["accent"]))
        painter.drawEllipse(QPointF(split_x, mid_y), 11, 11)
        painter.setPen(QPen(QColor(255, 255, 255), 1.6))
        for s in (-1, 1):
            painter.drawLine(QPointF(split_x + s * 2.5, mid_y - 4), QPointF(split_x + s * 6, mid_y))
            painter.drawLine(QPointF(split_x + s * 6, mid_y), QPointF(split_x + s * 2.5, mid_y + 4))
        painter.restore()
        fm = QFontMetrics(self.font())
        left = self._labels[0]
        self._draw_chip(painter, max(12, split_x - fm.horizontalAdvance(left) - 34), 12, left)
        self._draw_chip(painter, split_x + 12, 12, self._labels[1])

    def _draw_hud(self, painter: QPainter, ref_pm: QPixmap):
        zoom_pct = int(round(self.output_zoom() * 100))
        zoom_str = f"Fit · {zoom_pct}%" if self._is_fit_to_view else f"{zoom_pct}%"
        out_w, out_h = self._output_size or (ref_pm.width(), ref_pm.height())
        text = f"{zoom_str} of output pixels  ·  {out_w} × {out_h} px"
        if self._display_scale < 1.0:
            text += f"  ·  shown downsampled to {self._display_scale * 100:.0f}% (export unaffected)"
        fm = QFontMetrics(self.font())
        text = fm.elidedText(text, Qt.TextElideMode.ElideRight, max(60, self.width() - 40))
        r = QRectF(12, self.height() - fm.height() - 20, fm.horizontalAdvance(text) + 16, fm.height() + 8)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._colors["chip"])
        painter.drawRoundedRect(r, 5, 5)
        painter.setPen(self._colors["text"])
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def _paint_message(self, painter: QPainter, dim: bool = False):
        title, subtitle = self._message or ("", "")
        painter.save()
        if dim:
            c = QColor(self._colors["viewer"])
            c.setAlpha(170)
            painter.fillRect(self.rect(), c)
        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() * 1.35)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(self._colors["text"])
        cy = self.height() / 2.0
        painter.drawText(QRectF(16, cy - 44, self.width() - 32, 34), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, title)
        painter.setFont(self.font())
        painter.setPen(self._colors["muted"])
        painter.drawText(QRectF(24, cy - 4, self.width() - 48, 60),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, subtitle)
        painter.restore()


class PreviewView(QWidget):
    """Viewer frame with its toolbar."""
    crop_preview_requested = Signal()
    toggle_queue_requested = Signal()
    toggle_settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self.toolbar = QToolBar("Viewer", self)
        self.toolbar.setObjectName("viewerToolbar")
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        self.act_toggle_queue = QAction("Images", self)
        self.act_toggle_queue.setCheckable(True)
        self.act_toggle_queue.setChecked(True)
        self.act_toggle_queue.setToolTip("Show or hide the Images panel (Ctrl+Shift+I)")
        self.act_toggle_settings = QAction("Settings", self)
        self.act_toggle_settings.setCheckable(True)
        self.act_toggle_settings.setChecked(True)
        self.act_toggle_settings.setToolTip("Show or hide the Settings panel (Ctrl+Shift+S)")
        self.act_crop_preview = QAction("Preview Crop", self)
        self.act_crop_preview.setToolTip("Process the region at the centre of the view with the current settings "
                                         "(uses the same surrounding context as the export)")
        self.mode_group = QActionGroup(self)
        self.act_split = QAction("Split", self)
        self.act_split.setToolTip("Before/after split view (drag the divider)")
        self.act_side = QAction("Side by side", self)
        self.act_side.setToolTip("Before and after next to each other with the same zoom and position")
        for a in (self.act_split, self.act_side):
            a.setCheckable(True)
            self.mode_group.addAction(a)
        self.act_split.setChecked(True)
        self.act_fit = QAction("Fit", self)
        self.act_fit.setToolTip("Fit the image in the viewer (Ctrl+0)")
        self.act_100 = QAction("100%", self)
        self.act_100.setToolTip("One output pixel per screen pixel (Ctrl+1)")
        self.act_200 = QAction("200%", self)
        self.act_200.setToolTip("Two screen pixels per output pixel (Ctrl+2)")
        self.combo_bg = QComboBox(self)
        self.combo_bg.addItems(["Checkerboard", "White", "Black", "Grey"])
        self.combo_bg.setToolTip("Viewer background behind transparent pixels (not saved into exports)")
        self.combo_bg.setAccessibleName("Viewer background")

        # Order = priority: when the viewer is narrow, QToolBar moves the trailing items into its "»" menu
        self.toolbar.addAction(self.act_toggle_queue)
        self.toolbar.addAction(self.act_toggle_settings)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.act_crop_preview)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.act_split)
        self.toolbar.addAction(self.act_side)
        self.toolbar.addSeparator()
        for a in (self.act_fit, self.act_100, self.act_200):
            self.toolbar.addAction(a)
        self.toolbar.addSeparator()
        self.act_bg = self.toolbar.addWidget(self.combo_bg)
        # Panel toggles are icon-only (with tooltips/accessible names) to leave room for viewer actions
        for act in (self.act_toggle_queue, self.act_toggle_settings):
            btn = self.toolbar.widgetForAction(act)
            if btn is not None:
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                btn.setAccessibleName(act.toolTip())
        self.combo_bg.setMinimumContentsLength(8)
        outer.addWidget(self.toolbar)

        frame = QFrame(self)
        frame.setObjectName("viewerFrame")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        self.canvas = ViewportCanvas(frame)
        fl.addWidget(self.canvas)
        outer.addWidget(frame, 1)

        # Compatibility alias used by other modules/tests
        self.btn_crop_preview = _ActionProxy(self.act_crop_preview)

        self.act_split.triggered.connect(lambda: self._set_mode("split"))
        self.act_side.triggered.connect(lambda: self._set_mode("side_by_side"))
        self.act_fit.triggered.connect(self.canvas.zoom_to_fit)
        self.act_100.triggered.connect(lambda: self.canvas.set_output_zoom(1.0))
        self.act_200.triggered.connect(lambda: self.canvas.set_output_zoom(2.0))
        self.combo_bg.currentIndexChanged.connect(self._on_bg_changed)
        self.act_crop_preview.triggered.connect(self.crop_preview_requested.emit)
        self.act_toggle_queue.triggered.connect(self.toggle_queue_requested.emit)
        self.act_toggle_settings.triggered.connect(self.toggle_settings_requested.emit)

    def set_icons(self, icons: dict):
        for act, key in ((self.act_toggle_queue, "panel_left"), (self.act_split, "split"), (self.act_side, "sidebyside"),
                         (self.act_fit, "fit"), (self.act_crop_preview, "crop"), (self.act_toggle_settings, "panel_right")):
            act.setIcon(icons[key])
        ext = self.toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
        if ext is not None:
            ext.setIcon(icons["more"])
            ext.setToolTip("More viewer actions")

    def _set_mode(self, mode):
        self.canvas.set_view_mode(mode)
        if self.canvas._is_fit_to_view:
            self.canvas.zoom_to_fit()

    def _on_bg_changed(self, idx: int):
        modes = ["checkerboard", "white", "black", "gray"]
        if 0 <= idx < len(modes):
            self.canvas.set_bg_mode(modes[idx])

    def set_images(self, orig: Optional[Image.Image], proc: Optional[Image.Image],
                   output_size: Optional[Tuple[int, int]] = None, display_scale: float = 1.0):
        self.canvas.set_images(orig, proc, output_size=output_size, display_scale=display_scale)

    def set_actions_enabled(self, enabled: bool):
        self.act_crop_preview.setEnabled(enabled)


class _ActionProxy:
    """Lets older code and tests query the crop-preview action like a button."""

    def __init__(self, action: QAction):
        self._a = action

    def isEnabled(self):
        return self._a.isEnabled()

    def setEnabled(self, v):
        self._a.setEnabled(v)

    def click(self):
        self._a.trigger()
