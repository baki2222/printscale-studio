# Changelog

All notable changes to PrintScale Studio. Versions follow `MAJOR.MINOR.PATCH`. Releases before 1.0.6 were
built and tested privately, before the source was published.

## [1.0.6] - 2026-10-18

First public open-source release.

### Changed
- **Package contents:** the app now ships only the Qt modules it uses (QtCore, QtGui, QtWidgets, QtSvg). 1.0.5 also contained Qt Virtual Keyboard, Qt Quick/QML, Qt PDF, Qt Network/TLS and the software OpenGL renderer. They are now left out, because Qt Virtual Keyboard is GPL-3.0-only for open-source use. The packages are about 10% smaller, and image processing is unchanged.
- **Runtime dependency:** `PySide6-Essentials` 6.12.0 replaces the full `pyside6` meta-package.
- **Notices:** every package now contains a `licenses\` folder with:
  - the project license;
  - the LGPL-3.0/GPL-3.0 texts and Qt's third-party attributions;
  - Python's license and the bundled packages' license files;
  - ONNX Runtime and DirectML notices, plus the Real-ESRGAN and DejaVu (logo lettering) licenses;
  - a Qt source and relinking notice;
  - a dependency inventory.
- **Installer:** its support URL now points to this repository. Upgrades also replace the `licenses` folder.

### Added
- **Model download:** `scripts/fetch_models.py` downloads the ONNX models with pinned SHA-256 verification, atomic writes and retries. `models/manifest.json` records model provenance. Source mode also honours `PRINTSCALE_MODEL_DIR`.
- **Build tooling:** a project-relative PyInstaller spec, and a bundle check that fails on missing or excluded files. `packaged_smoke.py` runs 8 packaged-app checks using generated images.
- **Repository setup:** GitHub Actions CI and a release workflow, documentation, and contribution and security guidelines.
- **Tests:** a model-manifest consistency test, and a `gpu`-marked DirectML test that is skipped on machines without a DirectX 12 GPU.

## [1.0.5] - 2026-10-18

### Added
- **Brand icon:** the PrintScale Studio icon is used for the EXE, installer, Start menu and desktop shortcuts, title bar, taskbar and Alt+Tab.
- **About dialog:** **Help › About** shows the logo, with light lettering in the dark theme and dark lettering in the light theme.

### Fixed
- **Start-menu icon after upgrade:** the installer refreshes its own shortcuts after installing, so the Start menu does not keep a cached icon from an earlier version.
- **Build:** the build no longer deletes earlier release files from `dist/`.

## [1.0.4] - 2026-10-18

Fixes found during a visible walkthrough of the installed app.

### Fixed
- **Side-by-side view:** at 100% or more, the ORIGINAL pane could be blank. A clipping error let the right pane paint over the left one.
- **Cancelled preview:** a cancelled or failed crop preview relabelled the still-visible panes as ORIGINAL | RESULT.
- **Toolbar overflow button:** at narrow window widths it was only about 12 px wide; it is now 34 px.
- **Batch summary:** it showed mixed `/` and `\` paths, and the Details column ran off-screen. Paths are now normalised and the details wrap.
- **Light theme:** the overflow menu blended into the white panels. Menus now use a tinted surface in both themes.

## [1.0.3] - 2026-10-17

### Changed
- **Interface redesign:**
  - Images panel, comparison viewer and Settings panel in a resizable layout, with dark and light themes.
  - The Images panel collapses automatically on narrow windows.
  - Toolbar items that don't fit move into an overflow menu.
- **Preferences persist:** mode, format, DPI, sharpening, JPEG options, composition, size fields, GPU preference, theme, window geometry and panel layout. Invalid stored values fall back to their defaults one by one.
- **Crop preview:** it now processes the region under the viewer centre with 32 px of real surrounding context, and labels exactly which source region it shows.

## [1.0.2] - 2026-10-17

An audit of 1.0.1 found and fixed 19 defects.

### Fixed
- **Transparent PNG halos:** exports with "Fit with padding" had darkened semi-transparent pixels and squared alpha, which showed as grey halos around lettering.
- **Batch export** ignored the print-size settings.
- **Metadata-only mode** could write PNG data into a `.jpg` file, and vice versa.
- **16-bit greyscale input** was clipped instead of scaled.
- **AI tile seams:** tiles now use 32 px of discarded context and blend only with their neighbours.
- **Colour:** non-sRGB inputs could be relabelled as sRGB instead of being converted.
- **Batch Cancel** stopped only the current item.
- **Concurrency:** jobs could overlap, and closing the window during a job was unsafe.
- **File safety:** the app could overwrite files silently, delete before replacing, or use the source as the destination. Verification and cancellation are now strict.
- **JPEG/PNG resolution metadata:** a malformed EXIF entry could be mishandled, and PNG `eXIf` and Photoshop resolution info are now updated together with the other resolution fields.
- **Limits:** jobs are refused before processing when they exceed output-size or memory limits, and decompression-bomb protection stays on.
- **Package:** model files were duplicated three times, PyTorch pickle files shipped, and upgrades left stale files behind.
- **Wording and display:** misleading labels and messages were corrected, along with GPU/CPU device reporting and viewer accuracy.

## [1.0.1]

The first packaged build; this was the baseline for the 1.0.2 audit.
