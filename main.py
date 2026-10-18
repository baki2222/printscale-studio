"""
PrintScale Studio - Professional Windows Desktop Image Super-Resolution & Print Export Suite
Entry point for launching the application.
"""

import os
import sys
import ctypes

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from printscale import __version__
from printscale.ui.main_window import MainWindow


def configure_application_style(app):
    """Fusion renders identically at every display scale and in both themes; the colours come
    from printscale.ui.theme. The Windows UI font is kept, with a readable minimum size."""
    from PySide6.QtGui import QFont
    from printscale.ui.style import PrintScaleStyle
    app.setStyle(PrintScaleStyle())
    font = QFont(app.font())
    if sys.platform == "win32":
        font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    if font.pointSizeF() < 9.0:
        font.setPointSizeF(9.0)
    app.setFont(font)


def main():
    # Set Windows Application User Model ID for clean taskbar grouping
    try:
        if sys.platform == "win32":
            app_id = f"VitalRove.PrintScaleStudio.{__version__}"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

    # High-DPI scaling configuration
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    # Before any window exists, so the title bar, Alt+Tab and taskbar all get the brand icon
    from printscale.ui.branding import app_icon
    app.setWindowIcon(app_icon())
    configure_application_style(app)
    app.setApplicationName("PrintScale Studio")
    app.setApplicationDisplayName("PrintScale Studio")
    app.setOrganizationName("VitalRove")
    app.setApplicationVersion(__version__)

    window = MainWindow()

    if "--auto-test" in sys.argv:
        idx = sys.argv.index("--auto-test")
        if idx + 2 < len(sys.argv):
            input_file = sys.argv[idx + 1]
            output_file = sys.argv[idx + 2]
            window.is_auto_test = True
            window.show()

            from PySide6.QtCore import QTimer

            def option(name, default=None):
                return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default

            def apply_test_options():
                """QA hook: sets the same widgets a user would click, then exports normally."""
                cv = window.controls_view
                if "--cpu" in sys.argv:
                    cv.chk_gpu.setChecked(False)  # emits prefer_gpu_changed like a user click
                mode = option("--mode", "preserve")
                {"preserve": cv.rb_preserve, "ai_illustration": cv.rb_illustration,
                 "ai_photo": cv.rb_photo}[mode].setChecked(True)
                if option("--format") == "jpeg":
                    cv.rb_jpg.setChecked(True)
                if option("--size"):
                    w, h = (int(v) for v in option("--size").lower().split("x"))
                    cv.rb_dim_pixel.setChecked(True)
                    cv.chk_lock_aspect.setChecked(False)
                    cv.spin_px_w.setValue(w)
                    cv.spin_px_h.setValue(h)
                if option("--print-in"):
                    w, h = (float(v) for v in option("--print-in").lower().split("x"))
                    cv.rb_dim_print.setChecked(True)
                    cv.chk_lock_aspect.setChecked(False)
                    cv.combo_unit.setCurrentText("in")
                    cv.spin_print_w.setValue(w)
                    cv.spin_print_h.setValue(h)
                if "--metadata-only" in sys.argv:
                    cv.rb_dim_meta.setChecked(True)
                if option("--dpi"):
                    cv.spin_custom_dpi.setValue(int(option("--dpi")))

            def trigger_test_pipeline():
                window.queue_view.add_files([input_file])
                apply_test_options()
                window._export_selected_image(target_filepath=output_file)

            def write_result():
                result_path = option("--result-json")
                if result_path and window.last_export_result is not None:
                    import json
                    from dataclasses import asdict
                    with open(result_path, "w", encoding="utf-8") as f:
                        json.dump(asdict(window.last_export_result), f, indent=2, ensure_ascii=False)

            app.aboutToQuit.connect(write_result)

            QTimer.singleShot(300, trigger_test_pipeline)
            sys.exit(app.exec())

    # If file paths passed on command line, import them
    if len(sys.argv) > 1:
        initial_files = [arg for arg in sys.argv[1:] if os.path.isfile(arg)]
        if initial_files:
            window.queue_view.add_files(initial_files)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
