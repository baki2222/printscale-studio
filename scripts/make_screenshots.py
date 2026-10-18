"""
Regenerate the README screenshots (docs/images/*.png) from the real application window, using generated
artwork (no third-party images) and isolated settings in a temporary folder.

    python scripts/make_screenshots.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def make_artwork(path):
    from PIL import Image, ImageDraw, ImageFilter
    w, h = 1200, 1372
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([170, 120, 1030, 980], fill=(255, 196, 61, 255))                       # sun
    for i, c in enumerate([(52, 212, 231), (101, 85, 232), (72, 53, 183)]):        # hills
        y = 700 + i * 150
        d.polygon([(60, h - 120), (60, y + 60), (330, y - 90), (620, y + 40), (900, y - 120), (1140, y + 30),
                   (1140, h - 120)], fill=c + (255,))
    d.rounded_rectangle([60, h - 170, 1140, h - 120], 25, fill=(23, 33, 59, 255))
    for x in range(200, 1000, 130):                                                   # birds
        d.arc([x, 300 + (x % 3) * 40, x + 70, 340 + (x % 3) * 40], 200, 340, fill=(23, 33, 59, 255), width=10)
    alpha = img.getchannel("A").filter(ImageFilter.GaussianBlur(1.2))
    img.putalpha(alpha)
    img.save(path, dpi=(150, 150))


def main():
    from PySide6.QtWidgets import QApplication
    tmp = tempfile.mkdtemp(prefix="printscale_screens_")
    os.environ["APPDATA"] = os.path.join(tmp, "appdata")
    app = QApplication(sys.argv)
    import main as entry
    entry.configure_application_style(app)
    from printscale.ui import main_window as mw
    from printscale.ui.branding import app_icon
    app.setWindowIcon(app_icon())
    mw.SummaryDialog.exec = lambda self: 0
    art = os.path.join(tmp, "sunset-hills.png")
    make_artwork(art)

    win = mw.MainWindow()
    win.resize(1500, 920)
    win.show()
    win.queue_view.add_files([art])
    cv = win.controls_view
    cv.rb_dim_pixel.setChecked(True)
    cv.spin_px_w.setValue(4200)
    cv.spin_px_h.setValue(4800)
    cv.spin_custom_dpi.setValue(300)
    for _ in range(50):
        app.processEvents()
    win._export_selected_image(target_filepath=os.path.join(tmp, "sunset-hills_4200x4800_300dpi.png"))
    import time
    end = time.time() + 120
    while (win._active_worker is not None or win.last_export_result is None) and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    out_dir = os.path.join(ROOT, "docs", "images")
    os.makedirs(out_dir, exist_ok=True)
    for theme in ("dark", "light"):
        win._apply_theme(theme, save=False)
        for _ in range(30):
            app.processEvents()
        path = os.path.join(out_dir, f"screenshot-{theme}.png")
        win.grab().save(path)
        print(path)
    win.close()


if __name__ == "__main__":
    main()
