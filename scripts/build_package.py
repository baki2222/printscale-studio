"""
Build the PrintScale Studio Windows release from this checkout:

  1. verify the ONNX models (python scripts/fetch_models.py downloads them)
  2. PyInstaller one-folder build from PrintScaleStudio.spec
  3. check the bundle: models, brand assets, required Qt parts present, excluded Qt parts absent
  4. collect license/notice material into the app folder (scripts/collect_notices.py)
  5. portable ZIP and Inno Setup installer
  6. SHA256SUMS.txt, DEPENDENCIES.json and BUILD-INFO.json in dist/release-v<version>/

    python scripts/build_package.py             # local build
    python scripts/build_package.py --release   # also fail on incomplete notices (used by CI)

Earlier release files in dist/ are never deleted; only dist/PrintScaleStudio and build/ are replaced.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

REQUIRED_IN_BUNDLE = [
    "PySide6/Qt6Core.dll", "PySide6/Qt6Gui.dll", "PySide6/Qt6Widgets.dll", "PySide6/Qt6Svg.dll",
    "PySide6/QtSvg.pyd", "PySide6/plugins/platforms/qwindows.dll", "PySide6/plugins/imageformats/qsvg.dll",
    "PySide6/plugins/imageformats/qico.dll", "PySide6/plugins/iconengines/qsvgicon.dll",
    "onnxruntime/capi/onnxruntime.dll", "onnxruntime/capi/DirectML.dll",
    "printscale/assets/brand/PrintScaleStudio_Windows.ico", "printscale/assets/brand/PrintScaleStudio_Logo.svg",
    "printscale/assets/brand/PrintScaleStudio_Logo_Light.svg", "printscale/assets/brand/PrintScaleStudio_Icon.svg",
]
FORBIDDEN_IN_BUNDLE = ("qt6virtualkeyboard", "qtvirtualkeyboardplugin", "platforminputcontexts", "qt6quick",
                       "qt6qml", "qt6pdf", "qpdf.dll", "qt6network", "qtnetwork.pyd", "plugins/tls",
                       "networkinformation", "qt6opengl", "opengl32sw", "torch", "pytest")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def find_iscc():
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        shutil.which("iscc") or "",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    raise SystemExit("Inno Setup 6 (ISCC.exe) not found. Install it from https://jrsoftware.org/isinfo.php")


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "unknown"


def check_bundle(app_folder):
    internal = os.path.join(app_folder, "_internal")
    rel_files = []
    for d, _, files in os.walk(internal):
        for f in files:
            rel_files.append(os.path.relpath(os.path.join(d, f), internal).replace("\\", "/"))
    low = [r.lower() for r in rel_files]
    missing = [r for r in REQUIRED_IN_BUNDLE if r.lower() not in low]
    forbidden = sorted({r for r in rel_files for p in FORBIDDEN_IN_BUNDLE if p in r.lower()})
    if missing or forbidden:
        raise SystemExit(f"Bundle check failed.\n  missing: {missing}\n  must not ship: {forbidden}")

    from printscale.inference.models import MODEL_REGISTRY
    bundled = sorted(os.listdir(os.path.join(internal, "models")))
    expected = sorted(i.filename for i in MODEL_REGISTRY.values())
    if bundled != expected:
        raise SystemExit(f"Unexpected model files in package: {bundled}")
    for info in MODEL_REGISTRY.values():
        if sha256(os.path.join(internal, "models", info.filename)) != info.sha256:
            raise SystemExit(f"Bundled model hash mismatch: {info.filename}")
    brand_src = os.path.join(ROOT, "printscale", "assets", "brand")
    for name in os.listdir(brand_src):
        if sha256(os.path.join(brand_src, name)) != sha256(os.path.join(internal, "printscale", "assets", "brand", name)):
            raise SystemExit(f"Brand asset not bundled correctly: {name}")
    print(f"  bundle OK: {len(rel_files)} files, models and brand assets verified, excluded Qt parts absent")


def write_zip(app_folder, zip_path):
    base = os.path.dirname(app_folder)
    entries = []
    for d, _, files in os.walk(app_folder):
        for f in files:
            full = os.path.join(d, f)
            entries.append((os.path.relpath(full, base).replace("\\", "/"), full))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc, full in sorted(entries):
            zf.write(full, arc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", action="store_true", help="fail on incomplete notices (CI release builds)")
    ap.add_argument("--skip-installer", action="store_true")
    args = ap.parse_args()

    from printscale import __version__ as version
    import collect_notices
    dist = os.path.join(ROOT, "dist")
    app_folder = os.path.join(dist, "PrintScaleStudio")
    out_dir = os.path.join(dist, f"release-v{version}")
    print(f"PrintScale Studio {version} build from {ROOT}")

    print("\n[1/6] Verifying models")
    if subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "fetch_models.py"), "--check"]).returncode:
        raise SystemExit("Models missing or invalid. Run: python scripts/fetch_models.py")

    print("\n[2/6] PyInstaller")
    for p in (os.path.join(ROOT, "build"), app_folder):
        shutil.rmtree(p, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", dist, "--workpath", os.path.join(ROOT, "build"),
                    os.path.join(ROOT, "PrintScaleStudio.spec")], check=True, cwd=ROOT)

    print("\n[3/6] Checking bundle")
    check_bundle(app_folder)

    print("\n[4/6] Licenses and notices")
    for doc in ("README.md", "LICENSE", "THIRD_PARTY_LICENSES.md"):
        shutil.copy2(os.path.join(ROOT, doc), app_folder)
    inventory = collect_notices.collect(app_folder, strict=args.release)

    print("\n[5/6] Portable ZIP and installer")
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f"PrintScaleStudio_v{version}_Windows_x64_Portable.zip")
    write_zip(app_folder, zip_path)
    artifacts = [zip_path]
    if not args.skip_installer:
        iss = os.path.join(ROOT, "scripts", "installer.iss")
        subprocess.run([find_iscc(), f"/DMyAppVersion={version}", f"/O{out_dir}", iss], check=True)
        artifacts.append(os.path.join(out_dir, f"PrintScaleStudio_Setup_v{version}.exe"))

    print("\n[6/6] Checksums and inventory")
    json.dump(inventory, open(os.path.join(out_dir, "DEPENDENCIES.json"), "w", encoding="utf-8"), indent=1)
    info = {"product": "PrintScale Studio", "version": version, "commit": git_commit(),
            "built_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "python": sys.version.split()[0], "builder": os.environ.get("GITHUB_WORKFLOW_REF", "local"),
            "run": (f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/"
                    f"{os.environ['GITHUB_RUN_ID']}") if os.environ.get("GITHUB_RUN_ID") else "local"}
    json.dump(info, open(os.path.join(out_dir, "BUILD-INFO.json"), "w", encoding="utf-8"), indent=1)
    sums = []
    for p in artifacts + [os.path.join(out_dir, "DEPENDENCIES.json"), os.path.join(out_dir, "BUILD-INFO.json")]:
        sums.append(f"{sha256(p)}  {os.path.basename(p)}")
        print(f"  {os.path.basename(p)}: {os.path.getsize(p):,} bytes")
    open(os.path.join(out_dir, "SHA256SUMS.txt"), "w", encoding="ascii", newline="\n").write("\n".join(sums) + "\n")
    print("\n" + "\n".join(sums))
    print(f"\nRelease files: {out_dir}")


if __name__ == "__main__":
    main()
