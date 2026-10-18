# Third-party licenses and provenance

PrintScale Studio's own source code, documentation and brand artwork are © 2026 Baki Billah under the
[MIT License](LICENSE), except where noted below. The release packages also contain third-party software and
model weights under their own terms. Every release package ships these texts in its `licenses\` folder.

## Shipped in the Windows packages (installer and portable ZIP)

| Component | Version | License | Notes |
|---|---|---|---|
| Qt (QtCore, QtGui, QtWidgets, QtSvg, plugins, translations) | 6.12.0 | LGPL-3.0-only | Unmodified binaries from the PyPI wheel `PySide6-Essentials`. See "Qt and PySide6" below. |
| Qt for Python: PySide6, shiboken6 | 6.12.0 | LGPL-3.0-only | Same as above. |
| Qt's bundled third-party code (libpng, libjpeg, FreeType, HarfBuzz, PCRE2, zlib, libtiff, libwebp, …) | as shipped in Qt 6.12.0 | various permissive licenses | [LICENSES/qt-6.12.0-third-party/ATTRIBUTIONS.md](LICENSES/qt-6.12.0-third-party/ATTRIBUTIONS.md) |
| ONNX Runtime (`onnxruntime-directml`) | 1.24.4 | MIT | The wheel's `LICENSE`, `ThirdPartyNotices.txt` and `Privacy.md` are shipped. |
| DirectML (`DirectML.dll`, inside `onnxruntime-directml`) | 1.15.4 | Microsoft Software License Terms (DirectML) | Redistributed as shipped by Microsoft for use on Windows. [License](LICENSES/DirectML-1.15.4-LICENSE.txt) and [notices](LICENSES/DirectML-1.15.4-ThirdPartyNotices.txt), taken from the official `Microsoft.AI.DirectML` 1.15.4 package. |
| NumPy (with bundled OpenBLAS) | 2.4.6 | BSD-3-Clause and others | The wheel's license files are shipped. |
| Pillow | 13.0.0 | MIT-CMU | The wheel's license file is shipped. |
| Python runtime and standard library | 3.11 | PSF-2.0 (with notices for OpenSSL, libffi, bzip2, …) | Python's `LICENSE.txt` is shipped. |
| PyInstaller bootloader | 6.22.3 | GPL-2.0-or-later with the PyInstaller bootloader exception | The exception allows distributing the bootloader with programs under any license. |
| Real-ESRGAN models, converted to ONNX | models-v1 | BSD-3-Clause | See "Model weights" below. |
| Wordmark lettering in the logo | n/a | Bitstream Vera / DejaVu font license | The outlines are derived from DejaVu Sans. [License text](LICENSES/DejaVu-Bitstream-Vera-FONT_LICENSE.txt). |

Each package also contains `licenses\DEPENDENCIES.json`, a machine-readable inventory of these components.

### Qt and PySide6

- **License:** Qt and PySide6 are used under the GNU Lesser General Public License v3 ([LGPL-3.0](LICENSES/LGPL-3.0-only.txt), which incorporates the [GPL-3.0](LICENSES/GPL-3.0-only.txt)).
- **Modules shipped:** only the modules the app uses. Qt Virtual Keyboard (GPL-3.0-only for open-source use), Qt Quick/QML, Qt PDF, Qt Network/TLS and the software OpenGL renderer are excluded at build time. `scripts/build_package.py` fails if any of them is present.
- **Linking:** the Qt and PySide6 libraries are separate, unmodified DLL/PYD files in `_internal\PySide6` and `_internal\shiboken6`. You can replace them with your own builds, or rebuild the application from this repository against your own PySide6.
- **Corresponding source:** the exact source archives (qtbase, qtsvg, qtimageformats, qttranslations and pyside-setup 6.12.0) are mirrored unmodified as assets of the [third-party-sources-qt-6.12.0](https://github.com/baki2222/printscale-studio/releases/tag/third-party-sources-qt-6.12.0) release. They are also available at [download.qt.io](https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/). Each package's `licenses\QT-SOURCE-AND-RELINKING.txt` repeats this information, together with a written offer.

### Model weights

- **Upstream:** [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) by Xintao Wang et al.
- **License:** the upstream repository, including the release page that publishes the checkpoints, is under the [BSD 3-Clause License](LICENSES/Real-ESRGAN-BSD-3-Clause.txt) (Copyright (c) 2021, Xintao Wang). The project publishes no separate license for the checkpoint files, so they are redistributed under those BSD-3-Clause terms, with this attribution.

| ONNX file | Converted from (official release asset) | Checkpoint SHA-256 | ONNX SHA-256 |
|---|---|---|---|
| `RealESRGAN_x4plus_anime_6B.onnx` | [v0.2.2.4 `RealESRGAN_x4plus_anime_6B.pth`](https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth) | `f872d837d3c90ed2e05227bed711af5671a6fd1c9f7d7e91c911a61f155e99da` | `6b04d9c09399e24f2ad6171246f2c21da3571383561f46a4bb93b1f4c18af40f` |
| `RealESRGAN_x4plus.onnx` | [v0.1.0 `RealESRGAN_x4plus.pth`](https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth) | `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1` | `ec45cb356739c0086893db4e6fcfefb3dc0af087816a13175cae2386532db8ff` |

- **Conversion and parity checks:** the ONNX files were produced by this project with `scripts/convert_torch_to_onnx.py`. They are not upstream artifacts. See [docs/MODELS.md](docs/MODELS.md).
- **No endorsement:** PrintScale Studio is not affiliated with or endorsed by the Real-ESRGAN authors.

## Development tools (not shipped in the app)

| Component | License | Used for |
|---|---|---|
| BasicSR `RRDBNet` architecture definition, adapted in `scripts/convert_torch_to_onnx.py` | Apache-2.0 ([text](LICENSES/Apache-2.0.txt)), © Xintao Wang | Loading the checkpoints for conversion |
| PyTorch, ONNX | BSD-3-Clause, Apache-2.0 | Model conversion only |
| PyInstaller (apart from the bootloader above), pytest, ruff | GPL-2.0-or-later with exception, MIT, MIT | Packaging, tests and lint |
| Inno Setup | Inno Setup License | Building the installer |

## Trademarks

Windows, DirectML and DirectX are trademarks of Microsoft. Qt is a trademark of The Qt Company. They are
mentioned only to describe compatibility; no endorsement is implied.
