# PrintScale Studio brand assets

The SVG files are the editable masters: real vector paths and gradients on transparent backgrounds, with no embedded
bitmaps, fonts or scripts. The PNG files are renders of them.

| File | Use |
|---|---|
| `PrintScaleStudio_Icon.svg` | App icon (master) |
| `PrintScaleStudio_Windows.ico` | Windows icon: 16, 20, 24, 32, 40, 48, 64, 96, 128 and 256 px RGBA |
| `PrintScaleStudio_Logo.svg` | Logo with dark lettering (#17213B), for light backgrounds |
| `PrintScaleStudio_Logo_Light.svg` | Logo with light lettering (#F5F7FE), for dark backgrounds |
| `PrintScaleStudio_Icon_Mono_Dark.svg` / `_Mono_Light.svg` | One-colour icon variants |
| `PrintScaleStudio_Icon_1024.png`, `PrintScaleStudio_Logo_2400.png` | Raster renders (transparent) |

- **Colours:** violet #6555E8, deep violet #4835B7, cyan #34D4E7.
- **Clear space:** keep at least the icon frame's thickness around the mark, and use the original proportions.
- **Copies used by the app:** `printscale/assets/brand/` holds the files the app loads at run time. They are byte-identical copies of the icon, ICO and logo masters here.

The mark was developed from an AI-generated concept and redrawn as clean vector geometry. The wordmark lettering is
converted to outlines derived from DejaVu Sans; its font license is in [`FONT_LICENSE.txt`](FONT_LICENSE.txt). The
brand assets are © 2026 Baki Billah and are covered by the project's MIT License. If you fork the project and
distribute a modified app, please use your own name and icon so users can tell the projects apart.
