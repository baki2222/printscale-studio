"""Print release notes for a version: its CHANGELOG section plus install and checksum instructions.

    python scripts/release_notes.py 1.0.6 > notes.md
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def section(version):
    text = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.S | re.M)
    if not m:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    return m.group(1).strip()


def main(version):
    repo = os.environ.get("GITHUB_REPOSITORY", "baki2222/printscale-studio")
    run = os.environ.get("RUN_URL", "")
    print(section(version))
    print(f"""
## Install

- **Installer (recommended):** `PrintScaleStudio_Setup_v{version}.exe`. It installs for the current user (no administrator rights needed) and upgrades earlier versions in place, keeping your settings and exports.
- **Portable:** `PrintScaleStudio_v{version}_Windows_x64_Portable.zip`. Unzip it anywhere and run `PrintScaleStudio\\PrintScaleStudio.exe`.
- **Requirements:** Windows 11 x64; Windows 10 is untested. A DirectX 12 GPU is used for the AI modes when available; otherwise they run on the CPU.
- **Unsigned:** the files are not code-signed, so SmartScreen may warn. Check the hash first, then choose **More info › Run anyway**:
  `Get-FileHash .\\PrintScaleStudio_Setup_v{version}.exe` must match `SHA256SUMS.txt`.
- **Provenance:** `gh attestation verify <file> --repo {repo}` checks a file against its build-provenance attestation.

## Known limitations

- **Tested on:** one physical Windows 11 PC at 150% display scaling. Windows 10, other physical scaling levels, and drag and drop from File Explorer have not been tested for this release.
- **Taskbar pins:** a pin made with an older version may group separately; re-pin after upgrading.
- **CI coverage:** CI runs on GitHub-hosted runners without a GPU, so the DirectML GPU test is skipped there.

## Files

- **App and checksums:** installer, portable ZIP and `SHA256SUMS.txt`.
- **Inventories:** `DEPENDENCIES.json` (bundled components and licenses) and `BUILD-INFO.json` (commit and workflow run).
- **Third-party notices:** inside each package, in `licenses\\`. Qt source code: see the `third-party-sources-qt-6.12.0` release.
""")
    if run:
        print(f"Built by GitHub Actions from tag v{version}: {run}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1])
