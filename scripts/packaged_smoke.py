"""
Packaged-app smoke test. Runs the real PrintScaleStudio.exe through its --auto-test hook (which sets the
same widgets a user clicks and calls the normal export slot), with a fresh isolated APPDATA per run and a
Unicode/space path, then checks every output with independent parsing (raw PNG/JPEG bytes and Pillow).
Native dialogs and clicks are bypassed, so this is partial GUI coverage.

All inputs are generated here (no private or third-party artwork).

    python scripts/packaged_smoke.py dist/PrintScaleStudio/PrintScaleStudio.exe [--work DIR] [--require-gpu]

Exit code 0 means every check passed. Results are also written to <work>/smoke_results.json.
"""
import argparse
import hashlib
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image, ImageDraw

results = []


def check(name, ok, detail):
    results.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + " :: " + detail, flush=True)


def png_chunks(path):
    d = open(path, "rb").read()
    i, out = 8, []
    while i < len(d):
        n = struct.unpack(">I", d[i:i + 4])[0]
        out.append((d[i + 4:i + 8], d[i + 8:i + 8 + n]))
        i += 12 + n
    return out


def jpeg_parts(path):
    d = open(path, "rb").read()
    i, segs = 2, []
    while d[i + 1] != 0xDA:
        n = struct.unpack(">H", d[i + 2:i + 4])[0]
        segs.append((d[i + 1], d[i:i + 2 + n]))
        i += 2 + n
    return segs, d[i:]


def make_artwork(path):
    """Transparent PNG with antialiased shapes and semi-transparent edges (synthetic test artwork)."""
    img = Image.new("RGBA", (420, 480), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([30, 30, 390, 450], fill=(101, 85, 232, 255), outline=(52, 212, 231, 255), width=14)
    d.rectangle([120, 150, 300, 330], fill=(255, 196, 61, 200))
    d.polygon([(210, 60), (260, 140), (160, 140)], fill=(23, 33, 59, 255))
    img = img.resize((840, 960), Image.LANCZOS).resize((420, 480), Image.LANCZOS)  # soft alpha edges
    img.save(path, dpi=(72, 72))


def make_conflict_jpeg(path):
    """JPEG whose JFIF density (72) disagrees with its big-endian EXIF resolution (300)."""
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 120, 40)).save(buf, "JPEG", quality=90, dpi=(72, 72))
    data = buf.getvalue()
    data_offset = 8 + 2 + 3 * 12 + 4          # TIFF header + IFD (3 entries) + next-IFD pointer
    ifd = struct.pack(">H", 3)
    ifd += struct.pack(">HHII", 0x011A, 5, 1, data_offset)        # XResolution (RATIONAL)
    ifd += struct.pack(">HHII", 0x011B, 5, 1, data_offset + 8)    # YResolution (RATIONAL)
    ifd += struct.pack(">HHIHH", 0x0128, 3, 1, 2, 0)              # ResolutionUnit = inches
    tiff = b"MM\x00\x2a" + struct.pack(">I", 8) + ifd + struct.pack(">I", 0)
    tiff += struct.pack(">II", 300, 1) * 2
    app1 = b"Exif\x00\x00" + tiff
    seg = b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
    i = 2 + struct.unpack(">H", data[4:6])[0] + 2  # after SOI + APP0 (JFIF)
    open(path, "wb").write(data[:i] + seg + data[i:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exe")
    ap.add_argument("--work", default=None)
    ap.add_argument("--require-gpu", action="store_true", help="fail if the AI check does not run on DirectML")
    args = ap.parse_args()
    exe = os.path.abspath(args.exe)
    work = args.work or tempfile.mkdtemp(prefix="printscale smoke ")
    work = os.path.join(work, "নমুনা smoke & (1)")
    os.makedirs(work, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "QT_", "VIRTUAL_ENV"))}

    def run_exe(src, out, *opts):
        rj = out + ".result.json"
        run_env = dict(env, APPDATA=os.path.join(work, "appdata", os.path.basename(out)))
        os.makedirs(run_env["APPDATA"], exist_ok=True)
        t = time.time()
        p = subprocess.run([exe, "--auto-test", src, out, "--result-json", rj, *opts],
                           cwd=os.path.expanduser("~"), env=run_env, timeout=1200)
        r = json.load(open(rj, encoding="utf-8")) if os.path.exists(rj) else {}
        return p.returncode, time.time() - t, r

    src = os.path.join(work, "artwork নকশা.png")
    make_artwork(src)

    # 1. Preserve Artwork, fixed pixel canvas 4200x4800 at 500 DPI: size, pHYs, alpha kept
    out = os.path.join(work, "01 preserve 4200x4800 500dpi.png")
    rc, dt, r = run_exe(src, out, "--mode", "preserve", "--size", "4200x4800", "--dpi", "500")
    im = Image.open(out) if os.path.exists(out) else None
    ph = [c for t, c in png_chunks(out) if t == b"pHYs"] if im else []
    alpha = np.array(im.convert("RGBA"))[..., 3] if im else np.zeros(1)
    check("preserve 4200x4800 @ 500 DPI", rc == 0 and im is not None and im.size == (4200, 4800) and im.mode == "RGBA"
          and ph == [struct.pack(">IIB", 19685, 19685, 1)] and alpha.min() == 0 and alpha.max() == 255,
          f"exit {rc}, {dt:.1f}s, size {im.size if im else None}, pHYs {[struct.unpack('>IIB', c) for c in ph]}, "
          f"alpha range {int(alpha.min())}-{int(alpha.max())}, sha256 {hashlib.sha256(np.array(im).tobytes()).hexdigest()[:16] if im else ''}")

    # 2. AI Illustration (GPU preferred, CPU fallback allowed unless --require-gpu)
    out = os.path.join(work, "02 ai_illustration 840x960.png")
    rc, dt, r = run_exe(src, out, "--mode", "ai_illustration", "--size", "840x960", "--dpi", "300")
    im = Image.open(out) if os.path.exists(out) else None
    dev = r.get("device_used", "")
    check("AI Illustration 840x960 @ 300 DPI", rc == 0 and im is not None and im.size == (840, 960) and im.mode == "RGBA"
          and "Real-ESRGAN" in r.get("method_used", "") and (dev.startswith("DirectML") or not args.require_gpu),
          f"exit {rc}, {dt:.1f}s, device '{dev}', method '{r.get('method_used')}'")

    # 3. AI Photo on CPU to JPEG, with JFIF and EXIF resolution
    out = os.path.join(work, "03 ai_photo cpu.jpg")
    rc, dt, r = run_exe(src, out, "--mode", "ai_photo", "--cpu", "--size", "600x600", "--dpi", "600", "--format", "jpeg")
    im = Image.open(out) if os.path.exists(out) else None
    check("AI Photo CPU 600x600 @ 600 DPI JPEG", rc == 0 and im is not None and im.size == (600, 600)
          and r.get("device_used", "").startswith("CPU") and im.info.get("jfif_density") == (600, 600)
          and float(im.getexif().get(0x011A, 0)) == 600,
          f"exit {rc}, {dt:.1f}s, device '{r.get('device_used')}', jfif {im.info.get('jfif_density') if im else None}")

    # 4. Metadata-only PNG 300>400>500>600>300: one pHYs before IDAT, image data untouched
    orig_idat = b"".join(c for t, c in png_chunks(src) if t == b"IDAT")
    cur, steps = src, []
    for i, dpi in enumerate([300, 400, 500, 600, 300]):
        nxt = os.path.join(work, f"04 meta step{i} {dpi}.png")
        run_exe(cur, nxt, "--metadata-only", "--dpi", str(dpi))
        ch = png_chunks(nxt)
        names = [t for t, _ in ch]
        steps.append((dpi, names.count(b"pHYs"), names.index(b"pHYs") < names.index(b"IDAT")))
        cur = nxt
    same_idat = b"".join(c for t, c in png_chunks(cur) if t == b"IDAT") == orig_idat
    check("metadata-only PNG 300>400>500>600>300", all(s[1] == 1 and s[2] for s in steps) and same_idat
          and [c for t, c in png_chunks(cur) if t == b"pHYs"][0] == struct.pack(">IIB", 11811, 11811, 1),
          f"steps {steps}; IDAT identical: {same_idat}")

    # 5. Metadata-only JPEG: JFIF 72 / EXIF 300 conflict resolved to 600, scan data identical
    jsrc = os.path.join(work, "conflict jfif72 exif300.jpg")
    make_conflict_jpeg(jsrc)
    out = os.path.join(work, "05 conflict 600.jpg")
    rc, dt, r = run_exe(jsrc, out, "--metadata-only", "--dpi", "600")
    s_in, scan_in = jpeg_parts(jsrc)
    s_out, scan_out = jpeg_parts(out)
    jfif = [s for m, s in s_out if m == 0xE0][0]
    e = Image.open(out).getexif()
    check("metadata-only JPEG JFIF/EXIF conflict", rc == 0 and struct.unpack(">BHH", jfif[11:16]) == (1, 600, 600)
          and float(e[0x011A]) == 600 and float(e[0x011B]) == 600 and scan_in == scan_out,
          f"JFIF {struct.unpack('>BHH', jfif[11:16])}, EXIF {e.get(0x011A)}/{e.get(0x011B)}, scan identical {scan_in == scan_out}")

    # 6. JPEG export flattens transparency onto the default white background
    out = os.path.join(work, "06 preserve jpeg white.jpg")
    rc, dt, r = run_exe(src, out, "--mode", "preserve", "--size", "1050x1200", "--dpi", "300", "--format", "jpeg")
    im = Image.open(out)
    check("JPEG flattens alpha on white", rc == 0 and im.mode == "RGB" and min(im.getpixel((3, 3))) >= 250,
          f"mode {im.mode}, corner {im.getpixel((3, 3))}")

    # 7. An existing destination is never overwritten
    out = os.path.join(work, "01 preserve 4200x4800 500dpi.png")
    before = hashlib.sha256(open(out, "rb").read()).hexdigest()
    rc, dt, r = run_exe(src, out, "--mode", "preserve", "--size", "1000x1000", "--dpi", "300")
    after = hashlib.sha256(open(out, "rb").read()).hexdigest()
    check("existing destination preserved", before == after and r.get("output_path", "").endswith("_1.png"),
          f"unchanged {before == after}; saved as {os.path.basename(r.get('output_path', ''))}")

    leftovers = [n for n in os.listdir(work) if n.startswith(".printscale_")]
    check("no temporary files left", not leftovers, f"{leftovers}")

    json.dump({"exe": exe, "results": results}, open(os.path.join(work, "smoke_results.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    failed = [r for r in results if r["result"] != "PASS"]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
