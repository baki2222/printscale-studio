"""
Download the ONNX models (and optionally the upstream PyTorch checkpoints) listed in models/manifest.json.

Every file is downloaded over HTTPS to a temporary ".part" file, checked against its pinned size and SHA-256,
and only then moved into place, so an interrupted or tampered download never replaces a good file.
Files that are already present and match their hash are kept.

    python scripts/fetch_models.py                 # ONNX models into ./models
    python scripts/fetch_models.py --dest D:\\m     # another writable folder (see PRINTSCALE_MODEL_DIR)
    python scripts/fetch_models.py --checkpoints   # also the official .pth checkpoints (for conversion)
    python scripts/fetch_models.py --check         # verify only, download nothing

Exit code 0 means every requested file is present and verified.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "models", "manifest.json")
CHUNK = 1 << 20


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def is_valid(path, size, digest):
    return os.path.isfile(path) and os.path.getsize(path) == size and sha256_of(path) == digest


def download(url, dest, size, digest, retries=3):
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-HTTPS URL: {url}")
    part = dest + ".part"
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "printscale-studio-fetch-models"})
            h = hashlib.sha256()
            got = 0
            with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
                for block in iter(lambda: resp.read(CHUNK), b""):
                    out.write(block)
                    h.update(block)
                    got += len(block)
            if got != size or h.hexdigest() != digest:
                raise ValueError(f"verification failed for {os.path.basename(dest)}: got {got:,} bytes, "
                                 f"SHA-256 {h.hexdigest()}; expected {size:,} bytes, SHA-256 {digest}")
            os.replace(part, dest)  # atomic on the same volume
            return
        except (urllib.error.URLError, OSError, ValueError) as e:
            last_error = e
            if os.path.exists(part):
                os.remove(part)
            if attempt < retries:
                wait = 2 ** attempt
                print(f"  attempt {attempt} failed ({e}); retrying in {wait}s", flush=True)
                time.sleep(wait)
    raise RuntimeError(f"could not download {url} after {retries} attempts: {last_error}\n"
                       f"Retry later with: python scripts/fetch_models.py")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=os.path.join(ROOT, "models"), help="target folder (default: ./models)")
    ap.add_argument("--checkpoints", action="store_true", help="also fetch the upstream .pth checkpoints")
    ap.add_argument("--check", action="store_true", help="verify existing files only")
    ap.add_argument("--retries", type=int, default=3)
    args = ap.parse_args(argv)

    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    os.makedirs(args.dest, exist_ok=True)
    items = []
    for m in manifest["models"]:
        items.append((m["file"], m["url"], m["bytes"], m["sha256"]))
        if args.checkpoints:
            c = m["checkpoint"]
            items.append((c["file"], c["url"], c["bytes"], c["sha256"]))

    failures = 0
    for name, url, size, digest in items:
        path = os.path.join(args.dest, name)
        if is_valid(path, size, digest):
            print(f"OK       {name} ({size:,} bytes, sha256 {digest[:12]}...)")
            continue
        if args.check:
            print(f"MISSING  {name}" if not os.path.exists(path) else f"INVALID  {name} (size or SHA-256 mismatch)")
            failures += 1
            continue
        print(f"FETCH    {name} from {url}", flush=True)
        try:
            download(url, path, size, digest, args.retries)
            print(f"OK       {name} verified")
        except Exception as e:  # report every file, then fail
            print(f"ERROR    {e}", file=sys.stderr)
            failures += 1
    if failures:
        print(f"{failures} file(s) not verified.", file=sys.stderr)
        return 1
    print(f"All {len(items)} file(s) verified in {os.path.abspath(args.dest)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
