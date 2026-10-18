"""
PrintScale Studio - Job status and export bar
Stage text and device line elide instead of pushing buttons; the progress bar and Cancel
appear only while a job runs; export actions are enabled only when they can run.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QProgressBar, QPushButton, QFrame, QSizePolicy

from printscale.ui.widgets import ElidedLabel


class StatusBarView(QWidget):
    export_selected_clicked = Signal()
    export_all_clicked = Signal()
    cancel_clicked = Signal()
    preview_clicked = Signal()  # kept for compatibility; the crop preview lives in the viewer toolbar

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(self)
        frame.setObjectName("panel")
        outer.addWidget(frame)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(10)

        col = QVBoxLayout()
        col.setSpacing(2)
        self.lbl_stage = ElidedLabel("Ready", frame, Qt.TextElideMode.ElideRight)
        self.lbl_stage.setObjectName("stage")
        col.addWidget(self.lbl_stage)
        self.lbl_device = ElidedLabel("Device: not used yet", frame, Qt.TextElideMode.ElideRight)
        self.lbl_device.setObjectName("muted")
        col.addWidget(self.lbl_device)
        layout.addLayout(col, 1)

        self.progress_bar = QProgressBar(frame)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumWidth(80)
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.progress_bar.setAccessibleName("Job progress")
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.btn_cancel = QPushButton("Cancel", frame)
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.setToolTip("Stop the running job. Nothing is written for the cancelled item.")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self.cancel_clicked.emit)
        layout.addWidget(self.btn_cancel)

        self.btn_export_all = QPushButton("Export Queue", frame)
        self.btn_export_all.setToolTip("Export every image in the queue to a folder with the current settings")
        self.btn_export_all.clicked.connect(self.export_all_clicked.emit)
        layout.addWidget(self.btn_export_all)

        self.btn_export_sel = QPushButton("Export Selected", frame)
        self.btn_export_sel.setObjectName("primary")
        self.btn_export_sel.setToolTip("Process and save the selected image (Ctrl+E)")
        self.btn_export_sel.clicked.connect(self.export_selected_clicked.emit)
        layout.addWidget(self.btn_export_sel)

        # Compatibility alias: the old bottom-bar preview button no longer exists
        self.btn_preview = None
        self._running = False
        self._has_selection = False
        self._has_queue = False
        self._update_buttons()

    def set_icons(self, icons: dict):
        self.btn_cancel.setIcon(icons["cancel"])
        self.btn_export_all.setIcon(icons["queue"])
        self.btn_export_sel.setIcon(icons["export"])

    def set_stage(self, stage: str, error: bool = False):
        self.lbl_stage.setText(stage)
        name = "stageError" if error else "stage"
        if self.lbl_stage.objectName() != name:
            self.lbl_stage.setObjectName(name)
            self.lbl_stage.style().unpolish(self.lbl_stage)
            self.lbl_stage.style().polish(self.lbl_stage)

    def set_device_info(self, device_text: str):
        self.lbl_device.setText(f"Device: {device_text}")

    def set_progress(self, current: int, total: int = 100):
        if total > 0:
            self.progress_bar.setValue(int(round((current / total) * 100)))

    def set_inputs_available(self, has_selection: bool, has_queue: bool):
        self._has_selection = has_selection
        self._has_queue = has_queue
        self._update_buttons()

    def set_running_state(self, is_running: bool):
        self._running = is_running
        self.progress_bar.setVisible(is_running)
        self.btn_cancel.setVisible(is_running)
        self.btn_cancel.setEnabled(is_running)
        if not is_running:
            self.progress_bar.setValue(0)
        self._update_buttons()

    def _update_buttons(self):
        self.btn_export_sel.setEnabled(not self._running and self._has_selection)
        self.btn_export_all.setEnabled(not self._running and self._has_queue)
