"""Rebuild scholarly_translation/assets/tesseract/ from the official installer.

Downloads (or takes with --installer) the UB Mannheim installer pinned in
assets/tesseract/sources.json, checks its SHA-256, extracts it with 7-Zip,
checks every original file's hash, strips the debug information
(strip_pe.py) and checks every result against sources.json. With --write the
binaries are copied into the package folder; without it the script only
verifies that the committed files are reproducible. Needs 7-Zip and
``pip install pefile==2024.8.26``. Never runs at app runtime.

    python scripts/release/tesseract/build_bundle.py [--installer PATH] [--write]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
BUNDLE = REPO_ROOT / "scholarly_translation" / "assets" / "tesseract"
sys.path.insert(0, str(HERE))

from strip_pe import strip_file  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_7zip() -> str:
    for candidate in (shutil.which("7z"), os.path.join(os.environ.get("ProgramFiles", ""), "7-Zip", "7z.exe")):
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("7-Zip (7z.exe) is required to extract the NSIS installer")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--installer", help="a local copy of the installer (otherwise it is downloaded)")
    parser.add_argument("--write", action="store_true", help="copy the rebuilt binaries into the package")
    args = parser.parse_args(argv)
    spec = json.loads((BUNDLE / "sources.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        installer = Path(args.installer) if args.installer else tmp / "setup.exe"
        if not args.installer:
            request = urllib.request.Request(spec["installer"]["url"], headers={"User-Agent": "scholarly-translation-build"})
            installer.write_bytes(urllib.request.urlopen(request, timeout=300).read())
        if sha256(installer) != spec["installer"]["sha256"]:
            raise SystemExit("installer SHA-256 does not match sources.json")
        extracted, stripped = tmp / "x", tmp / "stripped"
        subprocess.run([find_7zip(), "x", "-y", f"-o{extracted}", str(installer)], check=True, capture_output=True)
        stripped.mkdir()
        failures = []
        for entry in spec["files"]:
            name = entry["path"]
            if sha256(extracted / name) != entry["original_sha256"]:
                failures.append(f"{name}: original differs")
                continue
            strip_file(extracted / name, stripped / name)
            if sha256(stripped / name) != entry["sha256"]:
                failures.append(f"{name}: stripped result differs")
            elif not args.write and sha256(BUNDLE / name) != entry["sha256"]:
                failures.append(f"{name}: committed file differs")
        if failures:
            raise SystemExit("\n".join(failures))
        if args.write:
            for entry in spec["files"]:
                shutil.copyfile(stripped / entry["path"], BUNDLE / entry["path"])
    print(f"{len(spec['files'])} files reproduced from the official installer" + (" and written" if args.write else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
