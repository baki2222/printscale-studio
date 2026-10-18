"""
PrintScale Studio - Application style
Fusion base style with one adjustment: QToolBar sizes its overflow ("»") button from
PM_ToolBarExtensionExtent (about 12 px in Fusion), which squeezed the themed button into a
sliver at narrow widths. A proxy style gives it room for its icon and padding.
"""

from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleFactory


class PrintScaleStyle(QProxyStyle):
    def __init__(self):
        super().__init__(QStyleFactory.create("Fusion"))

    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PixelMetric.PM_ToolBarExtensionExtent:
            return 34
        return super().pixelMetric(metric, option, widget)
