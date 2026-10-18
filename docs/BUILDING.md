# Building PrintScale Studio

Everything here runs on Windows 10/11 x64. Release builds are made by GitHub Actions; see
[Release builds](#release-builds-github-actions) below.

## Prerequisites

- **Python 3.11 x64** from [python.org](https://www.python.org/downloads/windows/). The release workflow uses it because its `LICENSE.txt` carries the notices for Python's bundled OpenSSL and libffi; `build_package.py --release` checks this.
- **Git**.
- **[Inno Setup 6](https://jrsoftware.org/isinfo.php)**, only for the installer. The build script finds `ISCC.exe` in the default per-machine or per-user location, or on `PATH`.

## Set up the source tree

```powershell
git clone https://github.com/baki2222/printscale-studio.git
cd printscale-studio
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt -c constraints.txt
python scripts/fetch_models.py
```

- **Pinned versions:**
  - `requirements.txt`: runtime.
  - `requirements-dev.txt`: tests, lint and PyInstaller.
  - `requirements-convert.txt`: model conversion only.
  - `constraints.txt`: every transitive package, at the versions used by CI and releases.
- **ONNX Runtime:** `onnxruntime-directml` includes the CPU execution provider. Do not also install the plain `onnxruntime` package; both provide the same `onnxruntime` module.
- **Models:** `scripts/fetch_models.py` downloads the two ONNX models (about 85 MB) and checks their SHA-256 before accepting them. See [MODELS.md](MODELS.md).

## Run and test

```powershell
python main.py                  # the app, from source
python -m pytest                # headless Qt (QT_QPA_PLATFORM=offscreen is set by tests/conftest.py)
python -m pytest -m "not gpu"   # skip the test that needs a real DirectX 12 GPU
python -m ruff check .
```

Without a DirectX 12 GPU, the AI tests run on the CPU, and the `gpu`-marked test is skipped with the reason.

## Build the installer and portable ZIP

```powershell
python scripts/build_package.py            # add --skip-installer if Inno Setup is not installed
python scripts/packaged_smoke.py dist\PrintScaleStudio\PrintScaleStudio.exe
```

`build_package.py` does the following:

1. Checks the models (`fetch_models.py --check`).
2. Runs PyInstaller with [`PrintScaleStudio.spec`](../PrintScaleStudio.spec): a one-folder build with the brand ICO as the EXE icon. It bundles `models/*.onnx` into `_internal\models` and `printscale/assets/brand` into `_internal\printscale\assets\brand`.
3. Checks the bundle:
   - **Must be present:** the required Qt parts (Core, Gui, Widgets, Svg, the Windows platform plugin, and the SVG/ICO plugins), ONNX Runtime with DirectML, both models with matching hashes, and all brand assets byte-identical.
   - **Must be absent:** the Qt modules the app does not use. These are Qt Virtual Keyboard (GPL-3.0-only for open-source use), Qt Quick/QML, Qt PDF, Qt Network/TLS and the software OpenGL renderer. The build fails if any of them is present.
4. Writes `licenses\` into the app folder (`scripts/collect_notices.py`):
   - the project license, `THIRD_PARTY_LICENSES.md` and `LICENSES/`;
   - Python's license and each bundled wheel's license files, plus ONNX Runtime's notices;
   - the PyInstaller bootloader license and the Qt source/relinking notice;
   - `DEPENDENCIES.json`.
5. Creates `dist\release-v<version>\PrintScaleStudio_v<version>_Windows_x64_Portable.zip`, and the installer from [`scripts/installer.iss`](../scripts/installer.iss) with `ISCC /DMyAppVersion=<version>`.
6. Writes `SHA256SUMS.txt`, `DEPENDENCIES.json` and `BUILD-INFO.json`, which records the commit, Python version and workflow run.

The build replaces only `build\` and `dist\PrintScaleStudio`. Earlier release folders in `dist\` are kept.

`packaged_smoke.py` runs the built EXE through its `--auto-test` hook, with an isolated `APPDATA` and a Unicode path. It uses generated test images only. The 8 checks cover:
- sizes and DPI metadata;
- AI and CPU paths;
- metadata-only editing of PNG and JPEG;
- JPEG flattening;
- no overwriting;
- no leftover temporary files.

Add `--require-gpu` on a machine with a DirectX 12 GPU.

### Installer details

- **Identity:** the installer keeps the same identity as earlier releases: AppId `{D37E6B20-5A38-4C23-9F9B-1B4422A5C7F0}`, app name and install folder.
- **Install location:** it installs per user to `%LOCALAPPDATA%\Programs\PrintScale Studio` and needs no administrator rights.
- **Upgrades:** upgrades replace `_internal` and `licenses`. User settings (`%APPDATA%\PrintScaleStudio`) and exports are never touched.
- **Shortcut icons:** shortcuts use the bundled ICO path. After installing, the installer asks the Windows shell to refresh its own two shortcuts, so the Start menu does not keep a cached older icon.

## Release builds (GitHub Actions)

- **Workflow:** `.github/workflows/release.yml` runs when a `v*` tag is pushed.
- **Steps:** it checks out that exact commit, then installs from `constraints.txt` and fetches the models. It runs the tests, builds with `--release` and runs the packaged smoke test. Finally it uploads the installer, the portable ZIP, `SHA256SUMS.txt`, `DEPENDENCIES.json` and `BUILD-INFO.json` to a **draft** release, with build-provenance attestations.
- **Publishing:** the release is published only after all of these steps succeed.

To make a release:

1. Update `printscale/__init__.py` (`__version__`) and `CHANGELOG.md`, open a pull request, and merge it when CI is green.
2. Tag the merge commit and push the tag:
   ```powershell
   git tag -a v1.0.7 -m "PrintScale Studio 1.0.7"
   git push origin v1.0.7
   ```
3. Watch the **Release** workflow. When it finishes, the release is published with its checksums.
