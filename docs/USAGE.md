# Using PrintScale Studio

## Window layout

- **Images panel (left):** Add Images, drag and drop, thumbnails and per-file status.
  - Hide it with the toolbar toggle or **View › Images Panel** (Ctrl+Shift+I).
  - Below about 1080 px of window width it collapses automatically.
- **Viewer (centre):**
  - **Split** or **Side by side** comparison; Fit / 100% / 200% of real output pixels (Ctrl+0/1/2, mouse wheel, drag to pan, double-click to fit).
  - Viewer background: checkerboard, white, black or grey.
  - **Preview Crop** processes the region under the viewer centre with the current settings, plus 32 px of real surrounding context.
- **Settings panel (right):** Processing, Output Size (with a live pixel and print-size summary), Composition, Enhancement and Export.
- **Status bar:** current stage, the device that ran the job, progress, Cancel, **Export Queue** and **Export Selected**.

## Processing modes

| Mode | Engine | Best for | Keep in mind |
|---|---|---|---|
| **Preserve Artwork** (default) | Lanczos-3 resampling; optional unsharp mask (off by default) | Logos, lettering, apparel graphics, textured artwork | Adds no detail and invents none. Edges are as soft as the source resolution implies. |
| **AI Illustration** | Real-ESRGAN x4plus anime 6B (ONNX), ×4, then Lanczos-3 to the exact target | Clean line art and flat-colour raster graphics | Sharper edges, but it can flatten fine texture and exaggerate faint edge fringes already in the source. Check the result on dark and light backgrounds. |
| **AI Photo** | Real-ESRGAN x4plus (ONNX), ×4, then Lanczos-3 to the exact target | Photographs and product shots | Can alter small lettering. |

- **When the AI models run:** only when the target is larger than the source. Otherwise the export uses Lanczos-3, and the summary says the model was not applied.
- **Tiling:** AI inference runs in 256 px tiles, with 32 px of discarded context and a 16 px cross-fade, so tile edges don't leave seams.

## Output size

- **Print size + DPI:** you enter the physical size; the pixels follow from it.
  - `pixels = round(inches × DPI)`
  - `pixels = round(cm / 2.54 × DPI)`
  - Changing the DPI changes the pixels, not the print size.
- **Pixel canvas + DPI:** you enter exact pixels; the print size follows (`inches = pixels / DPI`).
- **DPI metadata only:** rewrites only the stored resolution, in the source's own format.
  - **PNG:** exactly one `pHYs` chunk before the first `IDAT`; an existing `eXIf` resolution is updated to match.
  - **JPEG:** JFIF density, EXIF X/YResolution and ResolutionUnit, and Photoshop resolution info are updated together. The compressed image data stays byte-identical.
  - **Pixels:** decoded pixels and alpha are verified unchanged.

**14 × 16 in reference:**

| DPI | Pixels | Megapixels |
|---|---|---|
| 300 | 4200 × 4800 | 20.2 |
| 400 | 5600 × 6400 | 35.8 |
| 500 | 7000 × 8000 | 56.0 |
| 600 | 8400 × 9600 | 80.6 |

**Composition:**
- **Fit with padding** keeps the whole image. Padding is transparent for PNG, and the chosen background colour for JPEG.
- **Crop to fill** fills the canvas and trims the overflow.
- Neither one distorts the aspect ratio.

## Transparency and colour

- **Alpha is handled separately:** it is resampled with Lanczos-3 and never passed through an AI model.
- **No hidden-colour bleed:** before resampling, the colour of fully transparent pixels is replaced with nearby edge colours, so hidden black or white can't bleed into anti-aliased edges.
- **Semi-transparent pixels** are copied onto the output canvas exactly.
- **JPEG backgrounds:** JPEG has no transparency, so transparent areas are flattened onto the background colour shown in the Export section (white by default).
- **Colour profiles:**
  - Output is sRGB with an embedded sRGB ICC profile.
  - Inputs with an embedded non-sRGB RGB or CMYK profile are converted through it (perceptual intent).
  - Untagged RGB or grey input is treated as sRGB.
  - Untagged CMYK uses a simple conversion, and the summary reports it as approximate.
- **16-bit input** is reduced to 8 bits per channel, and the summary says so.

## Exporting

- **Verified saves:**
  - Exports are written to a temporary file in the destination folder.
  - The file is then reopened and checked: dimensions, DPI, format, a full decode, and transparency where expected.
  - Only then is it moved into place.
- **No overwrites:** an existing file with the same name is never replaced. A numbered name such as `_1` is used instead.
- **Cancelling:** stops the job without leaving partial or temporary files.
- **Batch:** **Export Queue** applies the current settings to every image in the queue and shows a per-file summary.
- **Upload-profile check:** every summary reports whether the saved file is within this profile, using its real byte size and dimensions:
  - PNG or JPEG;
  - at most 52,428,800 bytes (50 MB);
  - at most 23,000 px on either side.

  PrintScale Studio never changes size, format, alpha or quality to pass a limit, and this profile is not a statement about any particular platform's current rules.
- **Hard limits:**
  - Canvases above 30,000 px on either side are refused.
  - So are jobs whose estimated working memory exceeds the free RAM.
  - Pillow's decompression-bomb protection stays on for inputs.

## Settings

- **Where they're stored:** preferences are saved in `%APPDATA%\PrintScaleStudio\config.json`.
- **What's remembered:**
  - processing mode, format, DPI, sharpening, JPEG quality and background;
  - composition and size fields;
  - GPU preference and theme;
  - window size and panel layout.
- **Not restored:** "DPI metadata only" is never restored at start-up.
- **Bad values:** invalid stored values fall back to their defaults one by one.
- **Uninstalling** removes neither settings nor exports.
