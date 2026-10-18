"""
PrintScale Studio - Line icons drawn with QPainter at runtime.
No icon fonts or network resources; icons are rendered at the device pixel ratio so they
stay sharp at every display scale, and tinted to the active theme.
"""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPainterPath, QGuiApplication


def _pen(color, width=1.6):
    return QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _draw(name: str, p: QPainter, c: str):
    p.setPen(_pen(c))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == "add":
        p.drawLine(QPointF(8, 3.5), QPointF(8, 12.5))
        p.drawLine(QPointF(3.5, 8), QPointF(12.5, 8))
    elif name == "remove":
        p.drawLine(QPointF(3.5, 8), QPointF(12.5, 8))
    elif name == "clear":
        p.drawLine(QPointF(4, 4), QPointF(12, 12))
        p.drawLine(QPointF(12, 4), QPointF(4, 12))
    elif name == "image":
        p.drawRoundedRect(QRectF(2, 3, 12, 10), 1.5, 1.5)
        path = QPainterPath(QPointF(3, 12))
        path.lineTo(6.5, 8)
        path.lineTo(9, 10.5)
        path.lineTo(10.5, 9)
        path.lineTo(13, 12)
        p.drawPath(path)
        p.drawEllipse(QPointF(10.5, 6), 1.1, 1.1)
    elif name == "split":
        p.drawRoundedRect(QRectF(2, 3, 12, 10), 1.5, 1.5)
        p.drawLine(QPointF(8, 2), QPointF(8, 14))
    elif name == "sidebyside":
        p.drawRoundedRect(QRectF(1.5, 4, 5.5, 8), 1, 1)
        p.drawRoundedRect(QRectF(9, 4, 5.5, 8), 1, 1)
    elif name == "fit":
        for (x, y, dx, dy) in ((2.5, 2.5, 1, 1), (13.5, 2.5, -1, 1), (2.5, 13.5, 1, -1), (13.5, 13.5, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + 3.5 * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + 3.5 * dy))
    elif name == "crop":
        p.drawLine(QPointF(4.5, 1.5), QPointF(4.5, 11.5))
        p.drawLine(QPointF(4.5, 11.5), QPointF(14.5, 11.5))
        p.drawLine(QPointF(1.5, 4.5), QPointF(11.5, 4.5))
        p.drawLine(QPointF(11.5, 4.5), QPointF(11.5, 14.5))
    elif name == "export":
        p.drawLine(QPointF(8, 2.5), QPointF(8, 10))
        p.drawLine(QPointF(5, 5.5), QPointF(8, 2.5))
        p.drawLine(QPointF(11, 5.5), QPointF(8, 2.5))
        p.drawLine(QPointF(3, 9.5), QPointF(3, 13.5))
        p.drawLine(QPointF(3, 13.5), QPointF(13, 13.5))
        p.drawLine(QPointF(13, 13.5), QPointF(13, 9.5))
    elif name == "queue":
        for y in (4, 8, 12):
            p.drawLine(QPointF(5.5, y), QPointF(13.5, y))
            p.drawPoint(QPointF(2.8, y))
    elif name == "cancel":
        p.drawEllipse(QPointF(8, 8), 5.8, 5.8)
        p.drawLine(QPointF(5.8, 5.8), QPointF(10.2, 10.2))
        p.drawLine(QPointF(10.2, 5.8), QPointF(5.8, 10.2))
    elif name == "panel_left":
        p.drawRoundedRect(QRectF(2, 3, 12, 10), 1.5, 1.5)
        p.drawLine(QPointF(6, 3), QPointF(6, 13))
    elif name == "panel_right":
        p.drawRoundedRect(QRectF(2, 3, 12, 10), 1.5, 1.5)
        p.drawLine(QPointF(10, 3), QPointF(10, 13))
    elif name == "chevron_right":
        p.drawPolyline([QPointF(6, 4), QPointF(10, 8), QPointF(6, 12)])
    elif name == "chevron_down":
        p.drawPolyline([QPointF(4, 6), QPointF(8, 10), QPointF(12, 6)])
    elif name == "more":
        p.setBrush(QColor(c))
        for x in (4, 8, 12):
            p.drawEllipse(QPointF(x, 8), 1.1, 1.1)
    elif name == "drop":
        p.drawLine(QPointF(8, 2.5), QPointF(8, 10))
        p.drawLine(QPointF(5, 7), QPointF(8, 10))
        p.drawLine(QPointF(11, 7), QPointF(8, 10))
        p.drawRoundedRect(QRectF(2.5, 11, 11, 3), 1, 1)


def make_icon(name: str, color: str, disabled_color: str = None, size: int = 16) -> QIcon:
    screen = QGuiApplication.primaryScreen()
    dpr = max(1.0, screen.devicePixelRatio() if screen else 1.0, 2.0)
    icon = QIcon()
    for mode, col in ((QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, disabled_color or color)):
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 16.0, size / 16.0)
        _draw(name, painter, col)
        painter.end()
        icon.addPixmap(pm, mode)
    return icon
