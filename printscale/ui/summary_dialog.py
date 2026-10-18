"""
PrintScale Studio - Truthful Completion Summary Dialogs
Shows the export audit for the file actually saved on disk: dimensions, DPI, physical size,
alpha status, byte size, upload-profile check, applied processing, device and notes.
"""

import os
import subprocess
from typing import List, Tuple
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView
)

from printscale.core.pipeline import JobExecutionResult, CANCELLED_MESSAGE


class SummaryDialog(QDialog):
    def __init__(self, result: JobExecutionResult, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Verification Summary - PrintScale Studio")
        self.setMinimumWidth(560)
        self.result = result

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title reflects the verification that actually ran
        if result.verification_passed:
            title, color = "Export saved and verified", "#4caf50"
        else:
            title, color = "Export saved - verification reported problems", "#ff9800"
        lbl_title = QLabel(title, self)
        lbl_title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {color};")
        layout.addWidget(lbl_title)

        card = QFrame(self)
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setSpacing(10)

        cm_w = round(result.physical_width_in * 2.54, 2)
        cm_h = round(result.physical_height_in * 2.54, 2)
        mb = result.file_size_bytes / (1024 * 1024)
        rows = [
            ("Output File:", os.path.normpath(result.output_path)),
            ("Pixel Dimensions:", f"{result.target_width} × {result.target_height} pixels"),
            ("Print Resolution:", f"{result.output_dpi:.3f} DPI (read back from the saved file)"),
            ("Physical Print Size:", f"{result.physical_width_in} × {result.physical_height_in} in ({cm_w} × {cm_h} cm)"),
            ("Alpha Transparency:", "Yes (RGBA)" if result.has_alpha else "No (opaque)"),
            ("Format:", result.format),
            ("File Size:", f"{result.file_size_bytes:,} bytes ({mb:.2f} MiB)"),
            ("Upload Profile:", result.upload_message or "Not checked"),
            ("Processing Applied:", result.method_used),
            ("Engine / Device:", result.device_used),
        ]
        for i, (label, value) in enumerate(rows):
            grid.addWidget(QLabel(label), i, 0, Qt.AlignmentFlag.AlignTop)
            val = QLabel(value)
            val.setObjectName("summaryValue")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if label == "Upload Profile:" and result.upload_compliant is False:
                val.setStyleSheet("color: #f44336; font-weight: 600;")
            grid.addWidget(val, i, 1)

        layout.addWidget(card)

        notes = list(result.notes)
        if result.warning_message:
            notes.insert(0, result.warning_message)
        if notes:
            lbl_notes = QLabel("Notes:\n• " + "\n• ".join(notes), self)
            lbl_notes.setWordWrap(True)
            lbl_notes.setObjectName("note")
            layout.addWidget(lbl_notes)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_open_file = QPushButton("Open File", self)
        self.btn_open_file.clicked.connect(self._open_file)
        btn_layout.addWidget(self.btn_open_file)

        self.btn_open_folder = QPushButton("Open Output Folder", self)
        self.btn_open_folder.clicked.connect(self._open_folder)
        btn_layout.addWidget(self.btn_open_folder)

        self.btn_close = QPushButton("Close", self)
        self.btn_close.setObjectName("primary")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _open_file(self):
        if os.path.exists(self.result.output_path):
            os.startfile(self.result.output_path)

    def _open_folder(self):
        _reveal_in_explorer(self.result.output_path)


def _reveal_in_explorer(path: str):
    if path and os.path.exists(path):
        # Argument list (no shell) so spaces, Unicode and metacharacters in names are passed safely
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


class BatchSummaryDialog(QDialog):
    """Per-file outcome of a batch export, based on each job's verified result."""

    def __init__(self, results: List[Tuple[str, JobExecutionResult]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Export Summary - PrintScale Studio")
        self.setMinimumSize(820, 360)
        layout = QVBoxLayout(self)

        ok = sum(1 for _, r in results if r.success)
        cancelled = sum(1 for _, r in results if r.error_message == CANCELLED_MESSAGE)
        failed = len(results) - ok - cancelled
        header = QLabel(f"{ok} exported, {failed} failed, {cancelled} cancelled", self)
        header.setStyleSheet("font-size: 15px; font-weight: 700;")
        layout.addWidget(header)

        table = QTableWidget(len(results), 4, self)
        table.setHorizontalHeaderLabels(["Source", "Status", "Saved as / Error", "Details"])
        table.setWordWrap(True)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.verticalHeader().setVisible(False)
        hdr = table.horizontalHeader()
        for col in (0, 1):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for row, (src, r) in enumerate(results):
            full = os.path.normpath(r.output_path) if r.output_path else ""
            if r.success:
                status = "Exported" if r.verification_passed else "Exported (warnings)"
                where, tip = os.path.basename(full), full
                details = f"{r.target_width}×{r.target_height} px · {r.output_dpi:.1f} DPI · {r.file_size_bytes:,} bytes · {r.upload_message}"
            elif r.error_message == CANCELLED_MESSAGE:
                status, where, tip, details = "Cancelled", "No file written", "", ""
            else:
                status, where, tip, details = "Failed", r.error_message or "Unknown error", r.error_message or "", ""
            for col, (text, tooltip) in enumerate([(os.path.basename(src or ""), os.path.normpath(src) if src else ""),
                                                   (status, status), (where, tip), (details, details)]):
                item = QTableWidgetItem(text)
                item.setToolTip(tooltip)
                table.setItem(row, col, item)
        table.setColumnWidth(2, 260)
        table.resizeRowsToContents()
        layout.addWidget(table, 1)

        btn_close = QPushButton("Close", self)
        btn_close.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)
