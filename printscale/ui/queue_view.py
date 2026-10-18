"""
PrintScale Studio - Imported Images and Batch Queue
Thumbnails, elided names with full-path tooltips, per-item status, drag-and-drop import
and an explicit empty state. Actions are laid out so their labels always fit.
"""

import os
from typing import List, Optional
from PIL import Image, ImageOps

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel,
    QFrame, QFileDialog, QMessageBox, QStackedWidget, QSizePolicy, QAbstractItemView
)
from PySide6.QtGui import QPixmap, QImage, QDragEnterEvent, QDropEvent

from printscale.core.metadata import read_file_metadata, ImageMetadataInfo
from printscale.core.pipeline import validate_input_image
from printscale.ui.widgets import ElidedLabel

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.tif *.tiff);;PNG (*.png);;JPEG (*.jpg *.jpeg);;All files (*.*)"


class QueueItemWidget(QWidget):
    def __init__(self, filepath: str, meta: ImageMetadataInfo, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.meta = meta
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        self.lbl_thumb = QLabel(self)
        self.lbl_thumb.setFixedSize(44, 44)
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_thumbnail()
        layout.addWidget(self.lbl_thumb, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(1)
        self.lbl_name = ElidedLabel(os.path.basename(filepath), self)
        self.lbl_name.setStyleSheet("font-weight: 600;")
        info.addWidget(self.lbl_name)
        alpha = "transparent" if meta.has_alpha else "opaque"
        self.lbl_dims = ElidedLabel(f"{meta.width} × {meta.height} px · {meta.format} · {alpha}", self,
                                    Qt.TextElideMode.ElideRight)
        self.lbl_dims.setObjectName("muted")
        info.addWidget(self.lbl_dims)
        self.lbl_status = ElidedLabel("Ready", self, Qt.TextElideMode.ElideRight)
        self.lbl_status.setObjectName("faint")
        info.addWidget(self.lbl_status)
        layout.addLayout(info, 1)

    def _load_thumbnail(self):
        try:
            with Image.open(self.filepath) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((88, 88), Image.Resampling.LANCZOS)
                im = im.convert("RGBA")
                qim = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, QImage.Format.Format_RGBA8888).copy()
                pm = QPixmap.fromImage(qim)
                pm.setDevicePixelRatio(2.0)
                self.lbl_thumb.setPixmap(pm)
        except Exception:
            self.lbl_thumb.setText("—")

    def update_status(self, status_text: str, color: Optional[str] = None):
        self.lbl_status.setText(status_text)
        self.lbl_status.setStyleSheet(f"color: {color};" if color else "")


class QueueView(QWidget):
    image_selected = Signal(str)   # Emits filepath when user selects an item
    files_added = Signal(list)     # Emits list of filepaths added
    selection_cleared = Signal()   # Emitted when no image is selected any more

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumWidth(210)
        self._editing_enabled = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(self)
        frame.setObjectName("panel")
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Images", frame)
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()
        self.lbl_count = QLabel("0 files", frame)
        self.lbl_count.setObjectName("muted")
        header.addWidget(self.lbl_count)
        layout.addLayout(header)

        self.stack = QStackedWidget(frame)
        empty = QWidget(self.stack)
        el = QVBoxLayout(empty)
        el.setContentsMargins(6, 18, 6, 18)
        el.addStretch()
        self.lbl_empty_icon = QLabel(empty)
        self.lbl_empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(self.lbl_empty_icon)
        t = QLabel("No images yet", empty)
        t.setObjectName("panelTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(t)
        h = QLabel("Drop PNG, JPEG, WebP or TIFF files here, or use Add Images.", empty)
        h.setObjectName("muted")
        h.setWordWrap(True)
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        el.addWidget(h)
        el.addStretch()
        self.stack.addWidget(empty)

        self.list_widget = QListWidget(self.stack)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        self.list_widget.setAccessibleName("Imported images")
        self.stack.addWidget(self.list_widget)
        layout.addWidget(self.stack, 1)

        self.btn_add = QPushButton("Add Images…", frame)
        self.btn_add.setToolTip("Add images (Ctrl+O). You can also drag files onto this panel.")
        self.btn_add.clicked.connect(self._browse_and_add)
        layout.addWidget(self.btn_add)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_remove = QPushButton("Remove", frame)
        self.btn_remove.setToolTip("Remove the selected image from the queue (the file is not deleted)")
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear = QPushButton("Clear", frame)
        self.btn_clear.setToolTip("Remove all images from the queue (files are not deleted)")
        self.btn_clear.clicked.connect(self._clear_all)
        row.addWidget(self.btn_remove, 1)
        row.addWidget(self.btn_clear, 1)
        layout.addLayout(row)
        self._update_count()

    def set_icons(self, add_icon, remove_icon, clear_icon, drop_icon):
        self.btn_add.setIcon(add_icon)
        self.btn_remove.setIcon(remove_icon)
        self.btn_clear.setIcon(clear_icon)
        self.lbl_empty_icon.setPixmap(drop_icon.pixmap(QSize(36, 36)))

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._editing_enabled and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if os.path.isfile(u.toLocalFile())]
        if paths:
            self.add_files(paths)
            event.acceptProposedAction()

    def _browse_and_add(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Images", "", IMAGE_FILTER)
        if files:
            self.add_files(files)

    def add_files(self, filepaths: List[str]):
        added, problems = [], []
        existing = {os.path.normcase(os.path.abspath(p)) for p in self.get_all_filepaths()}
        for path in filepaths:
            if os.path.normcase(os.path.abspath(path)) in existing:
                continue  # already queued
            try:
                ok, msg, probe = validate_input_image(path)
                if not ok:
                    raise ValueError(msg)
                probe.close()
                meta = read_file_metadata(path)
                item = QListWidgetItem(self.list_widget)
                item_widget = QueueItemWidget(path, meta)
                item.setSizeHint(QSize(10, item_widget.sizeHint().height()))
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(path)
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, item_widget)
                added.append(path)
                existing.add(os.path.normcase(os.path.abspath(path)))
            except Exception as e:
                problems.append(f"{os.path.basename(path)}: {e}")
        self._update_count()
        if problems:
            QMessageBox.warning(self, "Some files were not added", "\n".join(problems[:12]))
        if added:
            self.files_added.emit(added)
            if self.list_widget.currentItem() is None and self.list_widget.count() > 0:
                self.list_widget.setCurrentRow(0)

    def _remove_selected(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.list_widget.takeItem(row)
            self._update_count()
            if self.list_widget.count() == 0 or self.list_widget.currentItem() is None:
                self.selection_cleared.emit()

    def _clear_all(self):
        self.list_widget.clear()
        self._update_count()
        self.selection_cleared.emit()

    def set_editing_enabled(self, enabled: bool):
        """Queue edits are locked while a job runs so the running job's inputs stay stable."""
        self._editing_enabled = enabled
        self.btn_add.setEnabled(enabled)
        self.setAcceptDrops(enabled)
        self._update_count()

    def _update_count(self):
        count = self.list_widget.count()
        self.lbl_count.setText(f"{count} {'file' if count == 1 else 'files'}")
        self.stack.setCurrentIndex(1 if count else 0)
        can_edit = count > 0 and self._editing_enabled
        self.btn_remove.setEnabled(can_edit)
        self.btn_clear.setEnabled(can_edit)

    def _on_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]):
        if current:
            self.image_selected.emit(current.data(Qt.ItemDataRole.UserRole))

    def get_selected_filepath(self) -> Optional[str]:
        current = self.list_widget.currentItem()
        return current.data(Qt.ItemDataRole.UserRole) if current else None

    def get_all_filepaths(self) -> List[str]:
        return [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list_widget.count())]

    def update_item_status(self, filepath: str, status_text: str, color: Optional[str] = None):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == filepath:
                w = self.list_widget.itemWidget(item)
                if isinstance(w, QueueItemWidget):
                    w.update_status(status_text, color)
                break
