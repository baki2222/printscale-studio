# Contributing to PrintScale Studio

Thanks for your interest. Bug reports with a clear reproduction, focused fixes, tests and documentation
improvements are the most helpful contributions.

## Before you start

- **Bugs:** search [existing issues](https://github.com/baki2222/printscale-studio/issues) first, then use the bug report form.
- **Larger changes:** for new modes, new formats, UI changes or new dependencies, open a feature request first so the approach can be agreed before you spend time on it.
- **Security problems:** do not open a public issue. Follow [SECURITY.md](SECURITY.md).

## Development setup

You need Windows 10/11 x64, [Python 3.11](https://www.python.org/downloads/windows/) and Git.

```powershell
git clone https://github.com/baki2222/printscale-studio.git
cd printscale-studio
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt -c constraints.txt
python scripts/fetch_models.py     # ONNX models, SHA-256 verified (see docs/MODELS.md)
python main.py
```

Building the installer and portable ZIP: [docs/BUILDING.md](docs/BUILDING.md).

## Tests and checks

```powershell
python -m ruff check .
python -m pytest
```

- **Headless:** the tests run with Qt's offscreen platform and use temporary folders and an isolated `APPDATA`. They never touch your real settings.
- **GPU test:** tests marked `gpu` need a DirectX 12 GPU and are skipped without one. CI runs on GitHub-hosted runners, which have no GPU, so the AI tests run there on the CPU.
- **Packaged smoke test:** if you change packaging, also run `python scripts/build_package.py` and then `python scripts/packaged_smoke.py dist\PrintScaleStudio\PrintScaleStudio.exe`.

## Guidelines

- **Image output must not change by accident.** PrintScale Studio promises exact pixel sizes, correct DPI metadata, preserved transparency and verified saves. If a change affects exported pixels or metadata, say so in the pull request and add or update a test that checks the saved file.
- **Preserve Artwork** must stay non-generative: no AI, and no detail is invented.
- **Style:** match the surrounding code. Lint is `ruff check` with the settings in `pyproject.toml`, with a 130-character line limit.
- **Test images:** use generated images or images you have the right to share. Do not commit customer artwork, downloaded samples or large binaries. Model weights and release binaries never go into Git.
- **Dependencies:** pin new dependencies in the `requirements*.txt` files and `constraints.txt`. Check the license, and update `THIRD_PARTY_LICENSES.md` if the dependency ships in the app.
- **Pull requests:** keep each one focused on a single change, with a description of what changed and how you tested it.

## Good first contributions

- Testing on Windows 10, at other display-scaling levels, and with drag and drop from File Explorer. These are listed as untested in the [troubleshooting notes](docs/TROUBLESHOOTING.md#known-limitations).
- Clearer messages, and documentation fixes.
- Additional tests for unusual PNG/JPEG metadata, using small generated files.

## License

By contributing, you agree that your contributions are licensed under the project's [MIT License](LICENSE).
