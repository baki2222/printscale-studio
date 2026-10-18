"""
PrintScale Studio - Dark and Light Themes
One stylesheet template filled from a palette, so both themes style every widget state
(hover, pressed, checked, focus, disabled, error) the same way. Sizes are in logical pixels
and scale with Qt's high-DPI handling; text sizes follow the application font.
"""

from PySide6.QtGui import QPalette, QColor

DARK = {
    "name": "dark",
    "window": "#16171b", "surface": "#1e1f25", "surface2": "#25262d", "surface3": "#2d2f37",
    "field": "#15161a", "border": "#34363f", "border_strong": "#474a55",
    "text": "#e7e8ed", "muted": "#9a9dab", "faint": "#6d707d", "disabled": "#5c5f6b",
    "accent": "#6366f1", "accent_hover": "#7477f4", "accent_pressed": "#5154d9", "accent_text": "#ffffff",
    "accent_soft": "#2a2b4a", "focus": "#8b8ef7",
    "success": "#34c38f", "warning": "#f0a43a", "danger": "#f0606a", "danger_soft": "#3a1f24",
    "viewer": "#101114",
}

LIGHT = {
    "name": "light",
    "window": "#eef0f4", "surface": "#ffffff", "surface2": "#f5f6f9", "surface3": "#e9ebf0",
    "field": "#ffffff", "border": "#d5d8e0", "border_strong": "#b9bdc8",
    "text": "#1d1f27", "muted": "#5d6170", "faint": "#8a8e9b", "disabled": "#a4a8b3",
    "accent": "#4f46e5", "accent_hover": "#5f57ea", "accent_pressed": "#4338ca", "accent_text": "#ffffff",
    "accent_soft": "#e7e6fb", "focus": "#4f46e5",
    "success": "#1f9d6c", "warning": "#b86e0b", "danger": "#d43b45", "danger_soft": "#fbe7e8",
    "viewer": "#dfe2e8",
}

_TEMPLATE = """
QMainWindow, QDialog {{ background: {window}; color: {text}; }}
QWidget {{ color: {text}; }}
QWidget:disabled {{ color: {disabled}; }}
QToolTip {{ background: {surface3}; color: {text}; border: 1px solid {border_strong}; padding: 4px 6px; }}

QMenuBar {{ background: {window}; color: {text}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; background: transparent; }}
QMenuBar::item:selected {{ background: {surface3}; }}
QMenu {{ background: {surface3}; border: 1px solid {border_strong}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {accent_soft}; color: {text}; }}
QMenu::item:disabled {{ color: {disabled}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 6px; }}

/* Panels */
QFrame#panel {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
QFrame#viewerFrame {{ background: {viewer}; border: 1px solid {border}; border-radius: 8px; }}
QFrame#card {{ background: {surface2}; border: 1px solid {border}; border-radius: 6px; }}
QLabel#panelTitle {{ font-weight: 600; color: {text}; }}
QLabel#sectionTitle {{ font-weight: 600; color: {text}; padding-top: 2px; }}
QLabel#muted, QLabel#hint {{ color: {muted}; }}
QLabel#faint {{ color: {faint}; }}
QLabel#summaryValue {{ color: {text}; font-weight: 600; }}
QLabel#ok {{ color: {success}; }}
QLabel#warn {{ color: {warning}; }}
QLabel#error {{ color: {danger}; }}
QLabel#note {{ background: {surface2}; border: 1px solid {border}; border-left: 3px solid {accent};
              border-radius: 4px; padding: 6px 8px; color: {muted}; }}
QLabel#stage {{ font-weight: 600; }}
QLabel#stageError {{ font-weight: 600; color: {danger}; }}
QFrame#hline {{ background: {border}; max-height: 1px; min-height: 1px; border: none; }}

/* Buttons */
QPushButton, QToolButton {{
    background: {surface3}; color: {text}; border: 1px solid {border_strong};
    border-radius: 6px; padding: 5px 12px; min-height: 22px;
}}
QToolButton {{ padding: 4px 8px; }}
QPushButton:hover, QToolButton:hover {{ background: {surface2}; border-color: {accent}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {surface}; }}
QPushButton:focus, QToolButton:focus {{ border: 1px solid {focus}; }}
QPushButton:checked, QToolButton:checked {{ background: {accent_soft}; border-color: {accent}; color: {text}; }}
QPushButton:disabled, QToolButton:disabled {{ background: {surface}; color: {disabled}; border-color: {border}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#flat {{ background: transparent; border: 1px solid transparent; }}
QToolButton#flat:hover {{ background: {surface3}; border-color: {border}; }}
QToolButton#flat:checked {{ background: {accent_soft}; border-color: {accent}; }}
QToolButton#sectionToggle {{ background: transparent; border: none; padding: 2px 0; font-weight: 600; color: {muted}; text-align: left; }}
QToolButton#sectionToggle:hover {{ color: {text}; }}

QPushButton#primary {{ background: {accent}; color: {accent_text}; border: 1px solid {accent}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#primary:pressed {{ background: {accent_pressed}; }}
QPushButton#primary:focus {{ border: 1px solid {focus}; }}
QPushButton#primary:disabled {{ background: {surface3}; color: {disabled}; border-color: {border}; }}
QPushButton#danger {{ color: {danger}; border-color: {danger}; background: {danger_soft}; }}
QPushButton#danger:hover {{ background: {danger}; color: {accent_text}; }}
QPushButton#danger:disabled {{ background: {surface}; color: {disabled}; border-color: {border}; }}
QPushButton#segment {{ border-radius: 5px; padding: 4px 6px; font-weight: 600; }}
QPushButton#segment:checked {{ background: {accent}; color: {accent_text}; border-color: {accent}; }}
QPushButton#segment:checked:disabled {{ background: {surface3}; color: {disabled}; border-color: {border}; }}

/* Fields */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {field}; color: {text}; border: 1px solid {border_strong}; border-radius: 5px;
    padding: 3px 6px; min-height: 22px; selection-background-color: {accent}; selection-color: {accent_text};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {faint}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {focus}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background: {surface}; color: {disabled}; border-color: {border};
}}
QSpinBox, QDoubleSpinBox {{ padding-right: 20px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right;
    width: 18px; border-left: 1px solid {border}; border-top-right-radius: 5px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right;
    width: 18px; border-left: 1px solid {border}; border-bottom-right-radius: 5px; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {surface3}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{arrow_up}"); width: 8px; height: 8px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{arrow_down}"); width: 8px; height: 8px; }}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{ image: none; }}
QComboBox {{ padding-right: 22px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 20px; border: none; }}
QComboBox::down-arrow {{ image: url("{arrow_down}"); width: 8px; height: 8px; }}
QComboBox QAbstractItemView {{ background: {surface}; border: 1px solid {border_strong};
    selection-background-color: {accent_soft}; selection-color: {text}; outline: none; padding: 2px; }}

/* Radio buttons and check boxes: explicit indicators so state is visible in both themes */
QRadioButton, QCheckBox {{ spacing: 8px; padding: 2px 0; background: transparent; }}
QRadioButton::indicator, QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {faint}; background: {field}; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator:hover, QCheckBox::indicator:hover {{ border-color: {accent}; }}
QRadioButton::indicator:focus, QCheckBox::indicator:focus {{ border-color: {focus}; }}
QRadioButton::indicator:checked {{ background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
    stop:0 {accent_text}, stop:0.38 {accent_text}, stop:0.45 {accent}, stop:1 {accent}); border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url("{check}"); }}
QRadioButton::indicator:disabled, QCheckBox::indicator:disabled {{ border-color: {border}; background: {surface}; }}
QRadioButton::indicator:checked:disabled {{ background: {border_strong}; border-color: {border_strong}; }}
QCheckBox::indicator:checked:disabled {{ background: {border_strong}; border-color: {border_strong}; }}
QRadioButton:focus, QCheckBox:focus {{ color: {text}; }}

/* Lists and tables */
QListWidget, QTableWidget {{ background: {surface}; border: none; outline: none; }}
QListWidget::item {{ border-radius: 6px; margin: 2px 0; }}
QListWidget::item:selected {{ background: {accent_soft}; border: 1px solid {accent}; }}
QListWidget::item:hover:!selected {{ background: {surface2}; }}
QHeaderView::section {{ background: {surface2}; color: {muted}; border: none; border-bottom: 1px solid {border}; padding: 4px 6px; }}
QTableWidget {{ gridline-color: {border}; border: 1px solid {border}; border-radius: 6px; }}

/* Scroll bars */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {border_strong}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {faint}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* Slider */
QSlider::groove:horizontal {{ height: 4px; background: {surface3}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {text}; border: 2px solid {accent}; width: 12px; height: 12px;
    margin: -6px 0; border-radius: 8px; }}
QSlider::handle:horizontal:focus {{ border-color: {focus}; }}
QSlider::sub-page:horizontal:disabled {{ background: {border_strong}; }}
QSlider::handle:horizontal:disabled {{ background: {surface3}; border-color: {border_strong}; }}

/* Progress */
QProgressBar {{ background: {surface3}; border: none; border-radius: 4px; text-align: center; color: {text};
    max-height: 8px; min-height: 8px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}

/* Splitter / toolbar */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {accent_soft}; }}
QToolBar {{ background: transparent; border: none; spacing: 4px; padding: 0; }}
QToolBar::separator {{ background: {border}; width: 1px; margin: 4px 4px; }}
QToolBarExtension {{ qproperty-icon: none; }}
"""

_ARROW_CACHE = {}


def _write_glyphs(p: dict) -> dict:
    """Small PNG glyphs (arrows, check mark) rendered locally in the theme colour for QSS url()."""
    import os
    import tempfile
    from PySide6.QtGui import QImage, QPainter, QPen, QPolygonF
    from PySide6.QtCore import Qt, QPointF

    key = p["name"]
    if key in _ARROW_CACHE:
        return _ARROW_CACHE[key]
    folder = os.path.join(tempfile.gettempdir(), "printscale_theme_glyphs")
    os.makedirs(folder, exist_ok=True)
    out = {}
    for name in ("arrow_up", "arrow_down", "check"):
        img = QImage(32, 32, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(p["accent_text"] if name == "check" else p["muted"])
        if name == "check":
            pen = QPen(color, 4.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline([QPointF(7, 17), QPointF(13, 23), QPointF(25, 9)])
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            pts = [QPointF(6, 21), QPointF(26, 21), QPointF(16, 9)] if name == "arrow_up" else \
                  [QPointF(6, 11), QPointF(26, 11), QPointF(16, 23)]
            painter.drawPolygon(QPolygonF(pts))
        painter.end()
        path = os.path.join(folder, f"{key}_{name}.png")
        img.save(path)
        out[name] = path.replace("\\", "/")
    _ARROW_CACHE[key] = out
    return out


def build_stylesheet(palette: dict) -> str:
    glyphs = _write_glyphs(palette)
    return _TEMPLATE.format(**palette, **glyphs)


def build_qpalette(p: dict) -> QPalette:
    """Base palette for widgets the stylesheet does not cover (e.g. native dialogs drawn by Qt)."""
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: p["window"], QPalette.ColorRole.WindowText: p["text"],
        QPalette.ColorRole.Base: p["field"], QPalette.ColorRole.AlternateBase: p["surface2"],
        QPalette.ColorRole.Text: p["text"], QPalette.ColorRole.Button: p["surface3"],
        QPalette.ColorRole.ButtonText: p["text"], QPalette.ColorRole.Highlight: p["accent"],
        QPalette.ColorRole.HighlightedText: p["accent_text"], QPalette.ColorRole.ToolTipBase: p["surface3"],
        QPalette.ColorRole.ToolTipText: p["text"], QPalette.ColorRole.PlaceholderText: p["faint"],
        QPalette.ColorRole.Link: p["accent"],
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(p["disabled"]))
    return pal


def palette_for(theme_name: str) -> dict:
    return LIGHT if theme_name == "light" else DARK


# Backwards-compatible names
DARK_THEME_QSS = None
LIGHT_THEME_QSS = None
