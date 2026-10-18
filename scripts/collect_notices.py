"""
Collect the license/notice material that must ship with a frozen PrintScale Studio build, and write a
dependency inventory. Used by build_package.py; can also be run on an existing dist folder:

    python scripts/collect_notices.py dist/PrintScaleStudio
"""
import importlib.metadata as md
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QT_SOURCES_RELEASE = "https://github.com/baki2222/printscale-studio/releases/tag/third-party-sources-qt-6.12.0"

# Python distributions whose code is bundled in the frozen app (runtime only; build/dev tools are not)
BUNDLED = {
    "pyside6-essentials": "Qt for Python (PySide6) runtime: QtCore, QtGui, QtWidgets, QtSvg and Qt 6 libraries",
    "shiboken6": "Qt for Python binding runtime",
    "numpy": "array maths (with bundled OpenBLAS)",
    "pillow": "image decoding/encoding",
    "onnxruntime-directml": "ONNX Runtime with the DirectML execution provider (includes DirectML.dll)",
}
# PyInstaller's bootloader is linked into PrintScaleStudio.exe
BOOTLOADER = "pyinstaller"


def dist_license_files(dist):
    files = []
    for f in dist.files or []:
        name = str(f).replace("\\", "/")
        low = name.lower()
        if ".dist-info/" in low and ("licen" in low or "copying" in low or "notice" in low):
            files.append(f)
    return files


def copy_dist_licenses(dist_name, dest):
    d = md.distribution(dist_name)
    out = os.path.join(dest, f"{d.metadata['Name']}-{d.version}")
    os.makedirs(out, exist_ok=True)
    copied = []
    for f in dist_license_files(d):
        src = d.locate_file(f)
        rel = str(f).replace("\\", "/").split(".dist-info/", 1)[1]
        target = os.path.join(out, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)
        copied.append(rel)
    return d, out, copied


def write_openssl_notice(app_folder, dest):
    """Python's Windows runtime ships OpenSSL 3 (Apache-2.0). Record the exact DLL versions next to the license."""
    import glob
    import pefile
    dlls = sorted(glob.glob(os.path.join(app_folder, "_internal", "lib*ssl*-3*.dll")) +
                  glob.glob(os.path.join(app_folder, "_internal", "libcrypto-3*.dll")))
    if not dlls:
        return None
    versions = {}
    for p in dlls:
        pe = pefile.PE(p, fast_load=True)
        pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        info = {}
        for fi in getattr(pe, "FileInfo", None) or []:
            for entry in fi:
                for st in getattr(entry, "StringTable", []):
                    info.update({k.decode(): v.decode(errors="replace") for k, v in st.entries.items()})
        pe.close()
        versions[os.path.basename(p)] = info.get("ProductVersion") or info.get("FileVersion") or "unknown"
    lines = "\n".join(f"  {name}: {ver}" for name, ver in versions.items())
    open(os.path.join(dest, "OpenSSL-NOTICE.txt"), "w", encoding="utf-8").write(
        "OpenSSL\n=======\n\nThis package contains OpenSSL libraries shipped with the Python runtime:\n"
        f"{lines}\n\nCopyright (c) 1998-2025 The OpenSSL Project Authors.\n"
        "Copyright (c) 1995-1998 Eric A. Young, Tim J. Hudson. All rights reserved.\n\n"
        "Licensed under the Apache License 2.0 (LICENSES/Apache-2.0.txt). Source: https://www.openssl.org/source/\n")
    return ", ".join(sorted(set(versions.values())))


def write_qt_notice(path, qt_version):
    text = f"""Qt {qt_version} and Qt for Python (PySide6 {qt_version}) in this package
==============================================================

PrintScale Studio uses Qt and PySide6 under the GNU Lesser General Public License v3
(see LICENSES/LGPL-3.0-only.txt and LICENSES/GPL-3.0-only.txt). Qt's third-party components and
their licenses are listed in LICENSES/qt-6.12.0-third-party/ATTRIBUTIONS.md.

Modules shipped: QtCore, QtGui, QtWidgets, QtSvg (Qt6Core.dll, Qt6Gui.dll, Qt6Widgets.dll, Qt6Svg.dll),
the PySide6/shiboken6 runtime, Qt platform/style/image-format/icon-engine plugins and Qt translations.
They are the unmodified binaries from the PyPI wheels PySide6-Essentials {qt_version} and shiboken6
{qt_version} published by The Qt Company.

Corresponding source code
-------------------------
The exact source archives for these binaries are mirrored, unmodified, as assets of:
  {QT_SOURCES_RELEASE}
  qtbase, qtsvg, qtimageformats, qttranslations (*-everywhere-src-{qt_version}.tar.xz) and
  pyside-setup-everywhere-src-{qt_version}.tar.xz
They are also available from The Qt Company:
  https://download.qt.io/official_releases/qt/6.12/{qt_version}/submodules/
  https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-{qt_version}-src/
If you cannot obtain them there, open an issue at https://github.com/baki2222/printscale-studio/issues
and the maintainer will provide them; this offer is valid for at least three years after the last
release that ships these binaries.

Replacing or relinking Qt
-------------------------
Qt and PySide6 are separate, dynamically loaded DLL/PYD files in _internal\\PySide6 and
_internal\\shiboken6; they are not statically linked or modified. To use a modified Qt, build Qt
{qt_version} (or a binary-compatible version) and PySide6 from the sources above and replace those
files, or rebuild PrintScale Studio from its MIT-licensed source with your own PySide6:
https://github.com/baki2222/printscale-studio (see docs/BUILDING.md).
"""
    open(path, "w", encoding="utf-8").write(text)


def collect(app_folder, strict=False):
    """Write <app_folder>/licenses and return the dependency inventory."""
    dest = os.path.join(app_folder, "licenses")
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    problems = []

    shutil.copy2(os.path.join(ROOT, "LICENSE"), os.path.join(dest, "PrintScale-Studio-LICENSE.txt"))
    shutil.copy2(os.path.join(ROOT, "THIRD_PARTY_LICENSES.md"), dest)
    shutil.copytree(os.path.join(ROOT, "LICENSES"), os.path.join(dest, "LICENSES"))
    shutil.copy2(os.path.join(ROOT, "models", "manifest.json"), os.path.join(dest, "models-manifest.json"))

    # Python runtime (python311.dll, standard library, and the libraries its Windows build includes)
    py_license = os.path.join(sys.base_prefix, "LICENSE.txt")
    shutil.copy2(py_license, os.path.join(dest, "Python-LICENSE.txt"))
    py_text = open(py_license, encoding="utf-8", errors="replace").read()
    if "libffi" not in py_text.lower():
        problems.append("Python LICENSE.txt does not mention libffi (use a python.org build for releases)")
    openssl = write_openssl_notice(app_folder, dest)

    inventory = []
    for name, role in BUNDLED.items():
        d, out, copied = copy_dist_licenses(name, os.path.join(dest, "python-packages"))
        expr = d.metadata.get("License-Expression") or d.metadata.get("License") or ""
        inventory.append({"name": d.metadata["Name"], "version": d.version, "license": expr.strip()[:200],
                          "role": role, "bundled": True, "license_files": copied})
        if name.startswith("onnxruntime"):
            pkg = os.path.join(os.path.dirname(d.locate_file("onnxruntime/__init__.py")))
            for f in ("LICENSE", "ThirdPartyNotices.txt", "Privacy.md"):
                if os.path.isfile(os.path.join(pkg, f)):
                    shutil.copy2(os.path.join(pkg, f), out)
            if not os.path.isfile(os.path.join(pkg, "ThirdPartyNotices.txt")):
                problems.append("onnxruntime ThirdPartyNotices.txt not found")
    b, _, copied = copy_dist_licenses(BOOTLOADER, os.path.join(dest, "build-tools"))
    inventory.append({"name": "pyinstaller", "version": b.version,
                      "license": "GPL-2.0-or-later WITH Bootloader-exception", "role": "bootloader linked into the EXE",
                      "bundled": True, "license_files": copied})
    inventory.append({"name": "Python", "version": sys.version.split()[0], "license": "PSF-2.0",
                      "role": "interpreter runtime (python311.dll, standard library)", "bundled": True,
                      "license_files": ["Python-LICENSE.txt"]})
    if openssl:
        inventory.append({"name": "OpenSSL", "version": openssl, "license": "Apache-2.0",
                          "role": "libcrypto/libssl shipped with the Python runtime", "bundled": True,
                          "license_files": ["OpenSSL-NOTICE.txt", "LICENSES/Apache-2.0.txt"]})
    inventory.append({"name": "DirectML","version": "1.15.4 (as shipped in onnxruntime-directml)",
                      "license": "Microsoft Software License Terms (DirectML)", "role": "GPU inference on DirectX 12",
                      "bundled": True, "license_files": ["LICENSES/DirectML-1.15.4-LICENSE.txt"]})
    inventory.append({"name": "Real-ESRGAN models (converted to ONNX)", "version": "models-v1", "license": "BSD-3-Clause",
                      "role": "AI Illustration / AI Photo weights", "bundled": True,
                      "license_files": ["LICENSES/Real-ESRGAN-BSD-3-Clause.txt", "models-manifest.json"]})
    inventory.append({"name": "PrintScale Studio brand assets", "version": "", "license": "MIT (project); wordmark outlines derived from DejaVu Sans (Bitstream Vera license)",
                      "role": "icon and logo", "bundled": True,
                      "license_files": ["LICENSES/DejaVu-Bitstream-Vera-FONT_LICENSE.txt"]})

    qt_version = md.version("pyside6-essentials")
    write_qt_notice(os.path.join(dest, "QT-SOURCE-AND-RELINKING.txt"), qt_version)
    json.dump(inventory, open(os.path.join(dest, "DEPENDENCIES.json"), "w", encoding="utf-8"), indent=1)
    if problems and strict:
        raise SystemExit("Notice collection failed:\n  " + "\n  ".join(problems))
    for p in problems:
        print("WARNING:", p)
    return inventory


if __name__ == "__main__":
    inv = collect(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist", "PrintScaleStudio"))
    print(json.dumps(inv, indent=1))
