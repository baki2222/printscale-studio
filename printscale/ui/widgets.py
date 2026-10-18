"""
PrintScale Studio - Small reusable layout widgets.
FlowLayout wraps items onto new rows instead of forcing a wider minimum width, and
CollapsibleSection hides secondary controls behind a labelled toggle.
"""

from PySide6.QtCore import Qt, QRect, QSize, QPoint, Signal
from PySide6.QtWidgets import (QLayout, QSizePolicy, QWidget, QVBoxLayout, QToolButton, QLabel, QFrame)
from PySide6.QtGui import QFontMetrics


class FlowLayout(QLayout):
    """Left-to-right layout that wraps to the next row when space runs out (Qt flow-layout pattern)."""

    def __init__(self, parent=None, h_spacing=6, v_spacing=6):
        super().__init__(parent)
        self._items = []
        self._h, self._v = h_spacing, v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = eff.x(), eff.y(), 0
        for item in self._items:
            if item.widget() is not None and not item.widget().isVisible() and not test_only:
                if item.widget().isHidden():
                    continue
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h
            if next_x - self._h > eff.right() + 1 and line_h > 0:
                x = eff.x()
                y += line_h + self._v
                next_x = x + hint.width() + self._h
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


class CollapsibleSection(QWidget):
    """A labelled toggle that shows or hides a block of secondary controls."""
    toggled = Signal(bool)

    def __init__(self, title: str, parent=None, expanded=False):
        super().__init__(parent)
        self._title = title
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.button = QToolButton(self)
        self.button.setObjectName("sectionToggle")
        self.button.setCheckable(True)
        self.button.setChecked(expanded)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setText(title)
        self.button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.button.setAccessibleName(title)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        lay.addWidget(self.button)
        lay.addWidget(self.body)
        self.body.setVisible(expanded)
        self.button.toggled.connect(self._on_toggled)

    def set_icons(self, collapsed_icon, expanded_icon):
        self._icons = (collapsed_icon, expanded_icon)
        self.button.setIcon(expanded_icon if self.button.isChecked() else collapsed_icon)

    def _on_toggled(self, on):
        self.body.setVisible(on)
        if hasattr(self, "_icons"):
            self.button.setIcon(self._icons[1] if on else self._icons[0])
        self.toggled.emit(on)


class ElidedLabel(QLabel):
    """Single-line label that elides with '…' instead of forcing its parent wider.
    The full text is always available as the tooltip."""

    def __init__(self, text="", parent=None, mode=Qt.TextElideMode.ElideMiddle):
        super().__init__(parent)
        self._full = ""
        self._mode = mode
        self._elides = True
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(40)
        self.setText(text)

    def setText(self, text):
        self._full = text or ""
        self.setToolTip(self._full)
        self._apply()

    def fullText(self):
        return self._full

    def text(self):
        return self._full

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply()

    def _apply(self):
        fm = QFontMetrics(self.font())
        QLabel.setText(self, fm.elidedText(self._full, self._mode, max(10, self.contentsRect().width())))

    def minimumSizeHint(self):
        return QSize(40, super().minimumSizeHint().height())


def hline(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("hline")
    f.setFrameShape(QFrame.Shape.NoFrame)
    f.setFixedHeight(1)
    return f
